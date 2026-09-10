"""Reading the game's own sprite inventory out of a `\\0PSL` layout.

The tool had been reverse-engineering sprite boundaries from pixels — Otsu
thresholds, connected components, guessing which blob was a card and which was
its frame. That was the wrong place to look. **The game already stores this.**
Every `id\\lsp\\...` resource is a layout, and it names each node and the
texture that node draws from:

    SysRoot
    ring_1    -> id\\texture\\jpn\\roulette\\roulette_001_ID_HQ
    waku1     -> id\\texture\\jpn\\roulette\\roulette_000_ID_HQ   (waku = frame)
    sitaji1   -> id\\texture\\jpn\\roulette\\roulette_000_ID_HQ   (sitaji = base)
    waku2, sitaji2, waku3, sitaji3, ...

So a sheet's contents can be listed exactly, by name, with no guessing: which
sprites exist, what each is called, and which texture it comes from.

**What is parsed here and what is not.** The header and the name table are
read. The node records themselves — which carry the source rectangle and the
placement — are *not* decoded: the project's own notes record that the node
format was never cracked, and this does not crack it either. What it gives
you is the inventory, which is enough to know what a sheet contains and what
still needs translating.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

PSL_MAGIC = b"\0PSL"
_RUN = re.compile(rb"[ -~]{3,}")
# Node names are identifiers: letters, digits and underscores. Anything else in
# the ASCII sweep is float/int payload that happens to fall in printable range.
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$|^[0-9]+_[0-9]+$")


@dataclass
class LayoutNode:
    name: str
    texture: str = ""

    @property
    def role(self) -> str:
        """What the Japanese node names mean, where they are recognisable."""

        lowered = self.name.lower()
        for prefix, meaning in (
            ("sysroot", "layout root"),
            ("waku", "frame"),
            ("sitaji", "backing plate"),
            ("moji", "lettering"),
            ("kage", "shadow"),
            ("hanko", "stamp"),
            ("ring", "ring"),
            ("icon", "icon"),
            ("base", "base"),
            ("bg", "background"),
            ("btn", "button"),
            ("cursor", "cursor"),
            ("line", "rule"),
            ("num", "number"),
            ("point", "pointer"),
        ):
            if lowered.startswith(prefix):
                return meaning
        if re.fullmatch(r"\d+_\d+", self.name):
            return "group"
        return ""


@dataclass
class Layout:
    name: str
    version: int
    node_count: int
    texture_count: int
    nodes: list[LayoutNode] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Did the sweep recover as many nodes as the header promises?"""

        return len(self.nodes) >= self.node_count

    def nodes_using(self, texture_name: str) -> list[LayoutNode]:
        tail = texture_name.replace("/", "\\").lower().split("\\")[-1]
        return [n for n in self.nodes
                if n.texture and n.texture.replace("/", "\\").lower().endswith(tail)]


def is_layout(raw: bytes) -> bool:
    return raw[:4] == PSL_MAGIC


def parse_layout(raw: bytes, name: str = "") -> Layout:
    """Header and name table. Node records are deliberately not interpreted."""

    if not is_layout(raw):
        raise ValueError("not a PSL layout")
    version = struct.unpack_from(">I", raw, 4)[0]
    node_count, texture_count = struct.unpack_from(">HH", raw, 12)

    nodes: list[LayoutNode] = []
    textures: list[str] = []
    seen: set[tuple[str, str]] = set()
    pending: str | None = None

    def flush(texture: str = "") -> None:
        nonlocal pending
        if pending is None:
            return
        key = (pending, texture)
        if key not in seen:
            seen.add(key)
            nodes.append(LayoutNode(name=pending, texture=texture))
        pending = None

    for match in _RUN.finditer(raw, 16):  # past the header, skipping the magic
        text = match.group().decode("ascii", "replace")
        reference = text.lstrip("+")
        lowered = reference.lower()
        if "\\texture\\" in lowered or "/texture/" in lowered:
            if reference not in textures:
                textures.append(reference)
            flush(reference)
            continue
        if len(text) <= 40 and _IDENT.match(text):
            flush()
            pending = text
    flush()

    # A name that appears both with and without a texture is one node listed
    # twice: once in the tree, once as an animation target. Keep the richer one.
    with_texture = {n.name for n in nodes if n.texture}
    nodes = [n for n in nodes if n.texture or n.name not in with_texture]

    return Layout(
        name=name,
        version=version,
        node_count=node_count,
        texture_count=texture_count,
        nodes=nodes,
        textures=textures,
    )


def layouts_in_archive(archive) -> list[Layout]:
    """Every layout resource in an open archive."""

    from alrummi3_core import unpack_entry

    out: list[Layout] = []
    for entry in archive.entries:
        try:
            raw = unpack_entry(entry)
        except Exception:
            continue
        if is_layout(raw):
            try:
                out.append(parse_layout(raw, entry.name))
            except Exception:
                continue
    return out


def describe_for_texture(archive, texture_name: str) -> list[str]:
    """What the layouts say about the sprites drawn from one texture."""

    lines: list[str] = []
    total = 0
    for layout in layouts_in_archive(archive):
        using = layout.nodes_using(texture_name)
        if not using:
            continue
        total += len(using)
        lines.append(f"{layout.name}  (PSL v0x{layout.version:X}, "
                     f"{layout.node_count} nodes)")
        for node in using:
            role = f"  — {node.role}" if node.role else ""
            lines.append(f"    {node.name}{role}")
    if not lines:
        return ["No layout in this archive references this texture by name."]
    return [f"{total} sprite(s) draw from this texture, named by the game:", ""] + lines
