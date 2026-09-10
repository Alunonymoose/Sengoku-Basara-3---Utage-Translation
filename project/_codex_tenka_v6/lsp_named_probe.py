from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


HEADER_SIZE = 16
NODE_SIZE = 176


def u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def s32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def f32be(data: bytes, offset: int) -> float:
    return struct.unpack_from(">f", data, offset)[0]


def read_u32_string(data: bytes, cursor: int) -> tuple[str, int]:
    length = u32be(data, cursor)
    cursor += 4
    end = cursor + length
    if length < 1 or end > len(data):
        raise ValueError(f"bad LSP string at 0x{cursor - 4:X}: {length}")
    value = data[cursor:end].rstrip(b"\0").decode("ascii", "replace")
    cursor = (end + 3) & ~3
    return value, cursor


def locate_name_table(data: bytes, count: int) -> int:
    minimum = HEADER_SIZE + count * NODE_SIZE
    marker = b"\0\0\0\x08SysRoot\0"
    offset = data.find(marker, minimum)
    if offset < 0:
        raise ValueError("SysRoot name table not found")
    return offset


def parse(path: Path) -> dict:
    data = path.read_bytes()
    count = struct.unpack_from(">H", data, 12)[0]
    cursor = locate_name_table(data, count)
    rows = []
    for index in range(count):
        record_offset = HEADER_SIZE + index * NODE_SIZE
        record = data[record_offset:record_offset + NODE_SIZE]
        name, cursor = read_u32_string(data, cursor)
        node_type = u32be(record, 0x54)
        texture = ""
        if node_type == 2:
            texture, cursor = read_u32_string(data, cursor)
        rows.append({
            "index": index,
            "record_offset": record_offset,
            "name": name,
            "texture": texture,
            "type": node_type,
            "position": [f32be(record, 0x00), f32be(record, 0x04)],
            "scale": [f32be(record, 0x20), f32be(record, 0x24)],
            "parent": s32be(record, 0x38),
            "size": [s32be(record, 0x48), s32be(record, 0x4C)],
            "material": s32be(record, 0x60),
            "geometry": [s32be(record, o) for o in (0x74, 0x78, 0x7C, 0x80)],
            "uv": [s32be(record, o) for o in (0x84, 0x88, 0x8C, 0x90)],
        })
    return {"path": str(path), "node_count": count, "tail_cursor": cursor, "nodes": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lsp", type=Path)
    parser.add_argument("--match", default="")
    args = parser.parse_args()
    result = parse(args.lsp)
    if args.match:
        needle = args.match.lower()
        result["nodes"] = [
            row for row in result["nodes"]
            if needle in row["name"].lower() or needle in row["texture"].lower()
        ]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
