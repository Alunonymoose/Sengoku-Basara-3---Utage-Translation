from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


HEADER_SIZE = 16
NODE_SIZE = 176


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from(">f", data, offset)[0]


def read_string(data: bytes, cursor: int) -> tuple[str, int]:
    length = u32(data, cursor)
    start = cursor + 4
    end = start + length
    if length < 1 or end > len(data):
        raise ValueError(f"bad string at 0x{cursor:X}: {length}")
    value = data[start:end].rstrip(b"\0").decode("ascii", "replace")
    return value, (end + 3) & ~3


def locate_names(data: bytes, count: int) -> int:
    marker = b"\0\0\0\x08SysRoot\0"
    offset = data.find(marker, HEADER_SIZE + count * NODE_SIZE)
    if offset < 0:
        raise ValueError("name table not found")
    return offset


def finite(value: float) -> float | str:
    if not math.isfinite(value):
        return repr(value)
    return round(value, 7)


def parse(path: Path) -> dict:
    data = path.read_bytes()
    count = struct.unpack_from(">H", data, 12)[0]
    aux_count = struct.unpack_from(">H", data, 14)[0]
    names_offset = locate_names(data, count)
    cursor = names_offset
    names: list[tuple[str, str]] = []
    for _ in range(count):
        name, cursor = read_string(data, cursor)
        texture, cursor = read_string(data, cursor)
        names.append((name, texture))

    rows = []
    for index, (name, texture) in enumerate(names):
        offset = HEADER_SIZE + index * NODE_SIZE
        record = data[offset:offset + NODE_SIZE]
        rows.append({
            "index": index,
            "record_offset": offset,
            "name": name,
            "texture": texture,
            "parent": s32(record, 0x38),
            "type": u32(record, 0x54),
            "ints": {f"0x{o:02X}": s32(record, o) for o in range(0, NODE_SIZE, 4)},
            "floats": {f"0x{o:02X}": finite(f32(record, o)) for o in range(0, NODE_SIZE, 4)},
        })

    tail_names = []
    tail_cursor = cursor
    while tail_cursor + 4 <= len(data):
        try:
            value, next_cursor = read_string(data, tail_cursor)
        except (ValueError, UnicodeDecodeError):
            break
        tail_names.append({"offset": tail_cursor, "value": value})
        if next_cursor <= tail_cursor:
            break
        tail_cursor = next_cursor

    return {
        "path": str(path),
        "size": len(data),
        "node_count": count,
        "aux_count": aux_count,
        "node_table_end": HEADER_SIZE + count * NODE_SIZE,
        "pre_name_offset": names_offset,
        "pre_name_size": names_offset - (HEADER_SIZE + count * NODE_SIZE),
        "node_names_end": cursor,
        "remaining_size": len(data) - cursor,
        "tail_names": tail_names,
        "tail_parse_end": tail_cursor,
        "nodes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--match", default="")
    parser.add_argument("--context", action="store_true")
    args = parser.parse_args()
    outputs = []
    for path in args.paths:
        parsed = parse(path)
        if args.match:
            needle = args.match.casefold()
            selected = [row for row in parsed["nodes"] if needle in row["name"].casefold() or needle in row["texture"].casefold()]
            if args.context:
                indices = {row["index"] for row in selected}
                indices |= {row["parent"] for row in selected if row["parent"] >= 0}
                indices |= {row["parent"] for row in parsed["nodes"] if row["parent"] in indices and row["parent"] >= 0}
                selected = [row for row in parsed["nodes"] if row["index"] in indices]
            parsed["nodes"] = selected
        outputs.append(parsed)
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
