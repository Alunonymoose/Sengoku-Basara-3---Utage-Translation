"""Conservative decoder for SB3/Utage PSL v0x21 animation/control tables.

This module is intentionally standalone from Alrummi3/layout.py while concurrent
work exists in the GPT worktree. It parses the animation table only when all
declared records land exactly on the node-name table. Otherwise it fails closed.

Evidence checkpoint: project/utage_harness/PSL_ANIMATION_RESEARCH_2026-09-30.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct

HEADER_SIZE = 16
NODE_SIZE = 176

# Channels alternate scalar/control and keyed tracks.
# 19 is provisionally 2 words/key: tested layouts land exactly, but no strong
# non-zero example has yet isolated this channel's payload width.
TRACK_STRIDE_WORDS = {
    1: 6,   # position
    3: 6,   # rotation
    5: 6,   # scale
    7: 6,   # secondary vector/rect-like track; exact-end proven
    9: 6,   # UV rect
    11: 3,  # color 0
    13: 3,  # color 1
    15: 3,  # color 2
    17: 3,  # color 3
    19: 2,  # unknown; width not independently exercised yet
    21: 3,  # unknown packed-value track; exact-end proven
}

CHANNEL_NAMES = {
    0: "control_0",
    1: "position",
    2: "control_2",
    3: "rotation",
    4: "control_4",
    5: "scale",
    6: "control_6",
    7: "vector_7",
    8: "control_8",
    9: "uv_rect",
    10: "control_10",
    11: "color_0",
    12: "control_12",
    13: "color_1",
    14: "control_14",
    15: "color_2",
    16: "control_16",
    17: "color_3",
    18: "control_18",
    19: "track_19",
    20: "control_20",
    21: "track_21",
}


def u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def s32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def locate_name_table(data: bytes, node_count: int) -> int:
    minimum = HEADER_SIZE + node_count * NODE_SIZE
    marker = b"\0\0\0\x08SysRoot\0"
    offset = data.find(marker, minimum)
    if offset < 0:
        raise ValueError("PSL SysRoot name table not found")
    return offset


@dataclass
class Key:
    time: int
    interpolation: int
    values: tuple[int, ...] = ()

    def float_values(self) -> tuple[float, ...]:
        return tuple(
            struct.unpack(">f", struct.pack(">I", value))[0]
            for value in self.values
        )


@dataclass
class Channel:
    index: int
    name: str
    scalar: int | None = None
    stride_words: int | None = None
    keys: list[Key] = field(default_factory=list)


@dataclass
class Record:
    index: int
    record_type: int
    target: int
    duration: int
    parent: int
    offset: int
    size: int
    channels: list[Channel] = field(default_factory=list)


@dataclass
class Table:
    records: list[Record]
    start: int
    end: int
    name_table_offset: int

    @property
    def exact(self) -> bool:
        return self.end == self.name_table_offset


def parse_record(
    data: bytes,
    cursor: int,
    index: int,
    limit: int,
    max_keys: int = 100_000,
) -> tuple[Record, int]:
    start = cursor
    if cursor + 12 > limit:
        raise ValueError(f"truncated PSL animation header {index}")
    record_type, target, duration = struct.unpack_from(">iii", data, cursor)
    cursor += 12

    channels: list[Channel] = []
    for channel_index in range(22):
        name = CHANNEL_NAMES[channel_index]
        if channel_index % 2 == 0:
            if cursor + 4 > limit:
                raise ValueError(
                    f"truncated PSL control {index}:{channel_index}"
                )
            scalar = u32be(data, cursor)
            cursor += 4
            channels.append(Channel(
                index=channel_index, name=name, scalar=scalar
            ))
            continue

        stride = TRACK_STRIDE_WORDS[channel_index]
        if cursor + 4 > limit:
            raise ValueError(
                f"truncated PSL key count {index}:{channel_index}"
            )
        count = u32be(data, cursor)
        cursor += 4
        if count > max_keys:
            raise ValueError(
                f"implausible PSL key count {count} "
                f"in animation {index}:{channel_index}"
            )
        byte_count = count * stride * 4
        if cursor + byte_count > limit:
            raise ValueError(
                f"PSL channel exceeds animation table "
                f"{index}:{channel_index} count={count} stride={stride}"
            )
        keys: list[Key] = []
        for _ in range(count):
            words = struct.unpack_from(
                ">" + "I" * stride, data, cursor
            )
            cursor += stride * 4
            keys.append(Key(
                time=words[0],
                interpolation=words[1],
                values=tuple(words[2:]),
            ))
        channels.append(Channel(
            index=channel_index,
            name=name,
            stride_words=stride,
            keys=keys,
        ))

    if cursor + 4 > limit:
        raise ValueError(f"truncated PSL animation trailer {index}")
    parent = s32be(data, cursor)
    cursor += 4

    return Record(
        index=index,
        record_type=record_type,
        target=target,
        duration=duration,
        parent=parent,
        offset=start,
        size=cursor - start,
        channels=channels,
    ), cursor


def parse_table(data: bytes) -> Table:
    if data[:4] != b"\0PSL":
        raise ValueError("not a PSL resource")
    if len(data) < HEADER_SIZE:
        raise ValueError("truncated PSL header")

    node_count, record_count = struct.unpack_from(">HH", data, 12)
    start = HEADER_SIZE + node_count * NODE_SIZE
    name_table_offset = locate_name_table(data, node_count)
    if start > name_table_offset:
        raise ValueError("PSL node table overlaps name table")

    cursor = start
    records: list[Record] = []
    for index in range(record_count):
        record, cursor = parse_record(
            data, cursor, index, name_table_offset
        )
        records.append(record)

    if cursor != name_table_offset:
        raise ValueError(
            f"PSL animation table ended at 0x{cursor:X}; "
            f"name table begins at 0x{name_table_offset:X}"
        )

    return Table(
        records=records,
        start=start,
        end=cursor,
        name_table_offset=name_table_offset,
    )
