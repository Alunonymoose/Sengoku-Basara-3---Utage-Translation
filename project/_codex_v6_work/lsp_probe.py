#!/usr/bin/env python3
"""Read-only structural probe for MT Framework PSL/LSP layout resources."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import struct
from pathlib import Path


NODE_SIZE = 176
HEADER_SIZE = 16


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def s32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big", signed=True)


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from(">f", data, offset)[0]


def finite_float(value: float) -> float | str:
    if not math.isfinite(value):
        return repr(value)
    return round(value, 6)


def node(data: bytes, index: int) -> dict:
    start = HEADER_SIZE + index * NODE_SIZE
    record = data[start : start + NODE_SIZE]
    words = [s32(record, offset) for offset in range(0, NODE_SIZE, 4)]
    floats = [finite_float(f32(record, offset)) for offset in range(0, NODE_SIZE, 4)]
    return {
        "index": index,
        "offset": start,
        "position": [finite_float(f32(record, 0)), finite_float(f32(record, 4))],
        "scale": [finite_float(f32(record, 0x20)), finite_float(f32(record, 0x24))],
        "parent": s32(record, 0x38),
        "links_3c_44": [s32(record, offset) for offset in (0x3C, 0x40, 0x44)],
        "size": [s32(record, 0x48), s32(record, 0x4C)],
        "id": s32(record, 0x50),
        "type": u32(record, 0x54),
        "fields_58_70": [s32(record, offset) for offset in range(0x58, 0x74, 4)],
        "material": s32(record, 0x60),
        "geometry": [s32(record, offset) for offset in (0x74, 0x78, 0x7C, 0x80)],
        "uv": [s32(record, offset) for offset in (0x84, 0x88, 0x8C, 0x90)],
        "fields_94_ac": [s32(record, offset) for offset in range(0x94, 0xB0, 4)],
        "words": words,
        "floats": floats,
        "sha256": hashlib.sha256(record).hexdigest(),
    }


def printable_strings(data: bytes, minimum: int = 4) -> list[dict]:
    results: list[dict] = []
    start = None
    for index, value in enumerate(data + b"\0"):
        printable = 0x20 <= value <= 0x7E
        if printable and start is None:
            start = index
        elif not printable and start is not None:
            if index - start >= minimum:
                results.append({
                    "offset": start,
                    "length": index - start,
                    "text": data[start:index].decode("ascii"),
                })
            start = None
    return results


def summarize(path: Path) -> dict:
    data = path.read_bytes()
    count = int.from_bytes(data[12:14], "big")
    aux_count = int.from_bytes(data[14:16], "big")
    nodes = [node(data, index) for index in range(count)]
    table_end = HEADER_SIZE + count * NODE_SIZE
    tail = data[table_end:]
    children: dict[int, list[int]] = collections.defaultdict(list)
    for item in nodes:
        children[item["parent"]].append(item["index"])
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "magic": data[:4].hex(),
        "version": u32(data, 4),
        "header_word_8": u32(data, 8),
        "node_count": count,
        "aux_count": aux_count,
        "node_table_end": table_end,
        "tail_size": len(tail),
        "type_counts": dict(sorted(collections.Counter(item["type"] for item in nodes).items())),
        "material_counts": dict(sorted(collections.Counter(item["material"] for item in nodes).items())),
        "root_nodes": children[-1],
        "nodes": nodes,
        "printable_strings": printable_strings(data),
        "tail_prefix_hex": tail[:512].hex(),
        "tail_suffix_hex": tail[-512:].hex(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = [summarize(path) for path in args.paths]
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
