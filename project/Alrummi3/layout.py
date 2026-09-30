"""Parser for MT Framework Lite PSL / .lsp sprite layouts.

SB3/Utage PSL v0x21 uses a 16-byte header, a 176-byte big-endian node
table, then an unaligned pair of counted strings (name, texture) per node.
The texture string may be empty. Geometry/UV fields are logical units;
Utage's texture-atlas coordinates map to physical XET pixels at 2x.
"""
from __future__ import annotations

import math
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
    node_id: int = 0

    parent: int = -1
    link_3c: int = -1
    link_40: int = -1
    link_44: int = -1
    position: tuple[float, float] = (0.0, 0.0)
    rotation: float = 0.0
    scale: tuple[float, float] = (1.0, 1.0)
    size: tuple[int, int] = (0, 0)
    shader_type: int = 0
    blend_state: int = 0
    geometry: tuple[int, int, int, int] = (0, 0, 0, 0)
    uv: tuple[int, int, int, int] = (0, 0, 0, 0)
    colors: tuple[int, int, int, int] = (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)

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

    @property
    def material(self) -> int:
        """Backward-compatible alias for the now identified mShaderType field."""
        return self.shader_type

    def source_rect(self, atlas_scale: float = 2.0) -> tuple[int, int, int, int]:
        return tuple(round(v * atlas_scale) for v in self.uv)

ANIMATION_CHANNELS = (
    ("control_0", None),
    ("position", 6),
    ("control_2", None),
    ("rotation", 6),
    ("control_4", None),
    ("scale", 6),
    ("control_6", None),
    ("geometry_rect", 6),
    ("control_8", None),
    ("uv_rect", 6),
    ("control_10", None),
    ("color_0", 3),
    ("control_12", None),
    ("color_1", 3),
    ("control_14", None),
    ("color_2", 3),
    ("control_16", None),
    ("color_3", 3),
    ("control_18", None),
    ("track_19", 2),
    ("control_20", None),
    ("visibility", 3),
)


@dataclass
class AnimationKey:
    time: int
    interpolation: int
    values: tuple[int, ...] = ()

    def float_values(self) -> tuple[float, ...]:
        return tuple(struct.unpack(">f", struct.pack(">I", v))[0] for v in self.values)


@dataclass
class AnimationChannel:
    index: int
    name: str
    stride_words: int | None
    keys: list[AnimationKey] = field(default_factory=list)
    scalar: int = 0


@dataclass
class AnimationRecord:
    index: int
    name: str
    record_type: int
    target_node: int
    duration: int
    parent_animation: int
    channels: list[AnimationChannel] = field(default_factory=list)
    offset: int = 0
    size: int = 0

    def channel(self, name: str) -> AnimationChannel:
        for channel in self.channels:
            if channel.name == name:
                return channel
        raise KeyError(name)


@dataclass
class Layout:
    name: str
    version: int
    node_count: int
    aux_count: int
    nodes: list[LayoutNode] = field(default_factory=list)
    animations: list[AnimationRecord] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)
    animation_table_offset: int = 0
    name_table_offset: int = 0
    name_table_end: int = 0
    animation_parse_error: str = ""
    aux_names: list[str] = field(default_factory=list)

    @property
    def texture_count(self) -> int:
        return len(self.textures)

    @property
    def animation_roots(self) -> list[AnimationRecord]:
        return [a for a in self.animations if a.parent_animation < 0]

    def animation_tree(self, root_index: int) -> list[AnimationRecord]:
        if not 0 <= root_index < len(self.animations):
            raise IndexError(root_index)
        wanted = {root_index}
        changed = True
        while changed:
            changed = False
            for anim in self.animations:
                if anim.index not in wanted and anim.parent_animation in wanted:
                    wanted.add(anim.index)
                    changed = True
        return [a for a in self.animations if a.index in wanted]

    @property
    def complete(self) -> bool:
        return len(self.nodes) == self.node_count

    def nodes_using(self, texture_name: str) -> list[LayoutNode]:
        tail = texture_name.replace("/", "\\").lower().split("\\")[-1]
        return [n for n in self.nodes if n.texture and
                n.texture.replace("/", "\\").lower().endswith(tail)]

    def node_by_id(self, node_id: int) -> LayoutNode | None:
        """Resolve the serialized PSL sprite ID, which is not the array index."""
        hits = [n for n in self.nodes if n.node_id == node_id]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            return None
        raise ValueError(f"duplicate PSL node id {node_id}: {[n.index for n in hits]}")

    def animation_target(self, animation: AnimationRecord) -> LayoutNode | None:
        """Resolve an animation record's serialized target ID to its sprite node."""
        if animation.target_node < 0:
            return None
        return self.node_by_id(animation.target_node)

    def mask_for(self, index: int) -> LayoutNode | None:
        """Resolve link_40 only when it targets a proven type-5 mask node."""
        target_id = self.nodes[index].link_40
        if target_id < 0:
            return None
        target = self.node_by_id(target_id)
        if target is not None and target.node_type == 5:
            return target
        return None

    def world_matrix(self, index: int) -> tuple[float, float, float, float, float, float]:
        """Return the hierarchical 2D affine matrix in logical screen coordinates."""
        visiting: set[int] = set()
        cache: dict[int, tuple[float, float, float, float, float, float]] = {}

        def mul(a, b):
            aa, ac, atx, ab, ad, aty = a
            ba, bc, btx, bb, bd, bty = b
            return (
                aa * ba + ac * bb,
                aa * bc + ac * bd,
                aa * btx + ac * bty + atx,
                ab * ba + ad * bb,
                ab * bc + ad * bd,
                ab * btx + ad * bty + aty,
            )

        def walk(i: int):
            if i < 0:
                return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
            if i in cache:
                return cache[i]
            if i in visiting or i >= len(self.nodes):
                raise ValueError(f"invalid/cyclic PSL parent at node {i}")
            visiting.add(i)
            node = self.nodes[i]
            parent = walk(node.parent)
            visiting.remove(i)
            r = math.radians(node.rotation)
            co, sn = math.cos(r), math.sin(r)
            sx, sy = node.scale
            local = (
                co * sx, -sn * sy, node.position[0],
                sn * sx,  co * sy, node.position[1],
            )
            value = mul(parent, local)
            cache[i] = value
            return value

        return walk(index)

    def world_transform(self, index: int) -> tuple[float, float, float, float]:
        """Compatibility pose: world origin plus affine axis magnitudes."""
        a, c, tx, b, d, ty = self.world_matrix(index)
        return tx, ty, math.hypot(a, b), math.hypot(c, d)

    def transformed_corners(self, index: int) -> list[tuple[float, float]]:
        node = self.nodes[index]
        a, c, tx, b, d, ty = self.world_matrix(index)
        x0, y0, x1, y1 = node.geometry
        return [
            (a * x + c * y + tx, b * x + d * y + ty)
            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        ]

    def logical_bbox(self, index: int) -> tuple[float, float, float, float]:
        points = self.transformed_corners(index)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)


def is_layout(raw: bytes) -> bool:
    return raw[:4] == PSL_MAGIC


def _parse_animation_record(
    raw: bytes, cursor: int, index: int, limit: int
) -> tuple[AnimationRecord, int]:
    start = cursor
    if cursor + 12 > limit:
        raise ValueError(f"truncated PSL animation header {index}")
    record_type, target_node, duration = struct.unpack_from(">iii", raw, cursor)
    cursor += 12
    channels: list[AnimationChannel] = []
    for channel_index, (channel_name, stride_words) in enumerate(ANIMATION_CHANNELS):
        if cursor + 4 > limit:
            raise ValueError(f"truncated PSL animation channel {index}:{channel_index}")
        if stride_words is None:
            scalar = _u32(raw, cursor)
            cursor += 4
            channels.append(AnimationChannel(
                index=channel_index, name=channel_name,
                stride_words=None, scalar=scalar))
            continue

        count = _u32(raw, cursor)
        cursor += 4
        if count > 100000:
            raise ValueError(
                f"implausible PSL key count {count} in animation {index}:{channel_index}")
        byte_count = count * stride_words * 4
        if cursor + byte_count > limit:
            raise ValueError(f"PSL animation channel exceeds table {index}:{channel_index}")
        keys: list[AnimationKey] = []
        for _ in range(count):
            words = struct.unpack_from(
                ">" + "I" * stride_words, raw, cursor)
            cursor += stride_words * 4
            keys.append(AnimationKey(
                time=words[0], interpolation=words[1],
                values=tuple(words[2:])))
        channels.append(AnimationChannel(
            index=channel_index, name=channel_name,
            stride_words=stride_words, keys=keys))

    if cursor + 4 > limit:
        raise ValueError(f"truncated PSL animation trailer {index}")
    parent_animation = _s32(raw, cursor)
    cursor += 4
    return AnimationRecord(
        index=index, name="", record_type=record_type,
        target_node=target_node, duration=duration,
        parent_animation=parent_animation, channels=channels,
        offset=start, size=cursor - start), cursor


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

    name_table_offset = _name_table_offset(raw, node_count)

    animations: list[AnimationRecord] = []
    animation_parse_error = ""
    if version == 0x21:
        try:
            animation_cursor = table_end
            for index in range(aux_count):
                animation, animation_cursor = _parse_animation_record(
                    raw, animation_cursor, index, name_table_offset)
                animations.append(animation)
            if animation_cursor != name_table_offset:
                raise ValueError(
                    f"PSL animation table ended at 0x{animation_cursor:X}, "
                    f"name table starts at 0x{name_table_offset:X}")
        except Exception as exc:
            # Preserve only the complete prefix for forensic inspection.
            # Rendering must still refuse incomplete animation tables.
            animation_parse_error = str(exc)

    cursor = name_table_offset
    names: list[tuple[str, str]] = []
    for _ in range(node_count):
        node_name, cursor = _read_string(raw, cursor)
        texture, cursor = _read_string(raw, cursor)
        names.append((node_name, texture))

    animation_names: list[str] = []
    if animations:
        for _ in range(aux_count):
            animation_name, cursor = _read_string(raw, cursor)
            animation_names.append(animation_name)
        for animation, animation_name in zip(animations, animation_names):
            animation.name = animation_name

    nodes: list[LayoutNode] = []
    textures: list[str] = []
    for index, (node_name, texture) in enumerate(names):
        off = HEADER_SIZE + index * NODE_SIZE
        rec = raw[off:off + NODE_SIZE]
        node = LayoutNode(
            index=index, name=node_name, texture=texture,
            node_type=_u32(rec, 0x54), node_id=_s32(rec, 0x50),
            parent=_s32(rec, 0x38),
            link_3c=_s32(rec, 0x3C), link_40=_s32(rec, 0x40),
            link_44=_s32(rec, 0x44),
            position=(_f32(rec, 0x00), _f32(rec, 0x04)),
            rotation=_f32(rec, 0x18),
            scale=(_f32(rec, 0x20), _f32(rec, 0x24)),
            size=(_s32(rec, 0x48), _s32(rec, 0x4C)),
            shader_type=_s32(rec, 0x60),
            blend_state=_s32(rec, 0x68),
            geometry=tuple(_s32(rec, o) for o in (0x74, 0x78, 0x7C, 0x80)),
            uv=tuple(_s32(rec, o) for o in (0x84, 0x88, 0x8C, 0x90)),
            colors=tuple(_u32(rec, o) for o in (0x94, 0x98, 0x9C, 0xA0)),
        )
        nodes.append(node)

        if texture and texture not in textures:
            textures.append(texture)

    return Layout(
        name=name, version=version, node_count=node_count,
        aux_count=aux_count, nodes=nodes, animations=animations,
        textures=textures, animation_table_offset=table_end,
        name_table_offset=name_table_offset,
        name_table_end=cursor,
        animation_parse_error=animation_parse_error,
        aux_names=animation_names,
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
            role = f"  ÔÇö {node.role}" if node.role else ""
            lines.append(
                f"    {node.name}{role}  uv={node.uv} "
                f"geom={node.geometry} pos={node.position}"
            )
    if not lines:
        return ["No layout in this archive references this texture by name."]
    return [f"{total} sprite(s) draw from this texture, named by the game:", ""] + lines
