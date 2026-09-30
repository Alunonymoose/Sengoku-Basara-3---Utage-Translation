"""Parser for MT Framework Lite PSL / .lsp sprite layouts.

SB3/Utage PSL v0x21 uses a 16-byte header, a 176-byte big-endian node
table, then an unaligned pair of counted strings (name, texture) per node.
The texture string may be empty. Geometry/UV fields are logical units;
Utage's texture-atlas coordinates map to physical XET pixels at 2x.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

PSL_MAGIC = b"\0PSL"
HEADER_SIZE = 16
NODE_SIZE = 176


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _s32(data: bytes, off: int) -> int:
    return struct.unpack_from(">i", data, off)[0]


def _f32(data: bytes, off: int) -> float:
    return struct.unpack_from(">f", data, off)[0]

def _read_string(data: bytes, cursor: int) -> tuple[str, int]:
    """Read an unaligned big-endian u32-length string."""
    if cursor + 4 > len(data):
        raise ValueError(f"truncated PSL string length at 0x{cursor:X}")
    length = _u32(data, cursor)
    cursor += 4
    end = cursor + length
    if length < 1 or end > len(data):
        raise ValueError(f"bad PSL string at 0x{cursor - 4:X}: {length}")
    value = data[cursor:end].rstrip(b"\0").decode("ascii", "replace")
    return value, end


def _name_table_offset(data: bytes, count: int) -> int:
    minimum = HEADER_SIZE + count * NODE_SIZE
    marker = b"\0\0\0\x08SysRoot\0"
    offset = data.find(marker, minimum)
    if offset < 0:
        raise ValueError("PSL SysRoot name table not found")
    return offset


@dataclass
class LayoutNode:
    index: int
    name: str
    texture: str = ""
    node_type: int = 0

    parent: int = -1
    link_3c: int = -1
    link_40: int = -1
    link_44: int = -1
    position: tuple[float, float] = (0.0, 0.0)
    rotation_deg: float = 0.0
    scale: tuple[float, float] = (1.0, 1.0)
    size: tuple[int, int] = (0, 0)
    material: int = 0
    geometry: tuple[int, int, int, int] = (0, 0, 0, 0)
    uv: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def role(self) -> str:
        lowered = self.name.lower()
        for prefix, meaning in (
            ("sysroot", "layout root"), ("waku", "frame"),
            ("sitaji", "backing plate"), ("moji", "lettering"),
            ("kage", "shadow"), ("hanko", "stamp"), ("ring", "ring"),
            ("icon", "icon"), ("base", "base"), ("bg", "background"),
            ("btn", "button"), ("cursor", "cursor"), ("line", "rule"),
            ("num", "number"), ("point", "pointer"), ("logo", "logo"),
        ):
            if lowered.startswith(prefix):
                return meaning
        if re.fullmatch(r"\d+_\d+", self.name):
            return "group"
        return ""

    def source_rect(self, atlas_scale: float = 2.0) -> tuple[int, int, int, int]:
        return tuple(round(v * atlas_scale) for v in self.uv)

@dataclass
class Layout:
    name: str
    version: int
    node_count: int
    aux_count: int
    nodes: list[LayoutNode] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)
    name_table_offset: int = 0
    name_table_end: int = 0
    aux_names: list[str] = field(default_factory=list)

    @property
    def texture_count(self) -> int:
        return self.aux_count

    @property
    def complete(self) -> bool:
        return len(self.nodes) == self.node_count

    def nodes_using(self, texture_name: str) -> list[LayoutNode]:
        tail = texture_name.replace("/", "\\").lower().split("\\")[-1]
        return [n for n in self.nodes if n.texture and
                n.texture.replace("/", "\\").lower().endswith(tail)]

    def world_matrix(self, index: int) -> tuple[float, float, float, float, float, float]:
        """Return 2D affine matrix (a,b,c,d,e,f) in logical screen coordinates."""
        visiting: set[int] = set()

        def mul(p, q):
            pa,pb,pc,pd,pe,pf = p
            qa,qb,qc,qd,qe,qf = q
            return (
                pa*qa + pb*qd, pa*qb + pb*qe, pa*qc + pb*qf + pc,
                pd*qa + pe*qd, pd*qb + pe*qe, pd*qc + pe*qf + pf,
            )

        def walk(i: int):
            if i < 0:
                return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
            if i in visiting or i >= len(self.nodes):
                raise ValueError(f"invalid/cyclic PSL parent at node {i}")
            visiting.add(i)
            n = self.nodes[i]
            parent = walk(n.parent)
            visiting.remove(i)
            r = math.radians(n.rotation_deg)
            co, si = math.cos(r), math.sin(r)
            sx, sy = n.scale
            local = (co*sx, -si*sy, n.position[0],
                     si*sx,  co*sy, n.position[1])
            return mul(parent, local)

        return walk(index)

    def world_transform(self, index: int) -> tuple[float, float, float, float]:
        """Compatibility pose: world origin plus axis magnitudes after rotation."""
        a,b,c,d,e,f = self.world_matrix(index)
        return c, f, math.hypot(a, d), math.hypot(b, e)

    def transformed_corners(self, index: int) -> list[tuple[float, float]]:
        n = self.nodes[index]
        a,b,c,d,e,f = self.world_matrix(index)
        x0,y0,x1,y1 = n.geometry
        return [(a*x+b*y+c, d*x+e*y+f)
                for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]

    def logical_bbox(self, index: int) -> tuple[float, float, float, float]:
        pts = self.transformed_corners(index)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)


def is_layout(raw: bytes) -> bool:
    return raw[:4] == PSL_MAGIC


def parse_layout(raw: bytes, name: str = "") -> Layout:
    if not is_layout(raw):
        raise ValueError("not a PSL layout")
    if len(raw) < HEADER_SIZE:
        raise ValueError("truncated PSL header")

    version = _u32(raw, 4)
    node_count, aux_count = struct.unpack_from(">HH", raw, 12)

    table_end = HEADER_SIZE + node_count * NODE_SIZE
    if table_end > len(raw):
        raise ValueError("PSL node table exceeds resource")

    cursor = _name_table_offset(raw, node_count)
    names: list[tuple[str, str]] = []
    for _ in range(node_count):
        node_name, cursor = _read_string(raw, cursor)
        texture, cursor = _read_string(raw, cursor)
        names.append((node_name, texture))

    nodes: list[LayoutNode] = []
    textures: list[str] = []
    for index, (node_name, texture) in enumerate(names):
        off = HEADER_SIZE + index * NODE_SIZE
        rec = raw[off:off + NODE_SIZE]
        node = LayoutNode(
            index=index, name=node_name, texture=texture,
            node_type=_u32(rec, 0x54), parent=_s32(rec, 0x38),
            link_3c=_s32(rec, 0x3C), link_40=_s32(rec, 0x40),
            link_44=_s32(rec, 0x44),
            position=(_f32(rec, 0x00), _f32(rec, 0x04)),
            rotation_deg=_f32(rec, 0x18),
            scale=(_f32(rec, 0x20), _f32(rec, 0x24)),
            size=(_s32(rec, 0x48), _s32(rec, 0x4C)),
            material=_s32(rec, 0x60),
            geometry=tuple(_s32(rec, o) for o in (0x74, 0x78, 0x7C, 0x80)),
            uv=tuple(_s32(rec, o) for o in (0x84, 0x88, 0x8C, 0x90)),
        )
        nodes.append(node)

        if texture and texture not in textures:
            textures.append(texture)

    name_table_end = cursor
    aux_names: list[str] = []
    aux_cursor = cursor
    for _ in range(aux_count):
        try:
            value, aux_cursor = _read_string(raw, aux_cursor)
        except ValueError:
            break
        aux_names.append(value)

    return Layout(
        name=name, version=version, node_count=node_count,
        aux_count=aux_count, nodes=nodes, textures=textures,
        name_table_offset=_name_table_offset(raw, node_count),
        name_table_end=name_table_end, aux_names=aux_names,
    )


def layouts_in_archive(archive) -> list[Layout]:
    from alrummi3_core import unpack_entry
    out: list[Layout] = []
    for entry in archive.entries:
        try:
            raw = unpack_entry(entry)
        except Exception:
            continue
        if not is_layout(raw):
            continue
        try:
            out.append(parse_layout(raw, entry.name))
        except Exception:
            continue
    return out


def describe_for_texture(archive, texture_name: str) -> list[str]:
    lines: list[str] = []
    total = 0
    for layout in layouts_in_archive(archive):
        using = layout.nodes_using(texture_name)

        if not using:
            continue
        total += len(using)
        lines.append(
            f"{layout.name}  (PSL v0x{layout.version:X}, "
            f"{layout.node_count} nodes)"
        )
        for node in using:
            role = f"  — {node.role}" if node.role else ""
            lines.append(
                f"    {node.name}{role}  uv={node.uv} "
                f"geom={node.geometry} pos={node.position}"
            )
    if not lines:
        return ["No layout in this archive references this texture by name."]
    return [f"{total} sprite(s) draw from this texture, named by the game:", ""] + lines
