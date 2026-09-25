#!/usr/bin/env python3
"""Read and inspect MT Framework rAscii / \0CSA resources.

The payload contract proven for current Utage fixtures is:
    0x00 4 bytes  \0CSA
    0x04 u32 BE   unknown field (observed 100)
    0x08 128 * u16 BE codepoint->glyph slots

This utility is read-only unless another tool explicitly uses encode_csa().
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

MAGIC = b"\x00CSA"
ENTRY_COUNT = 128
SIZE = 8 + ENTRY_COUNT * 2
UNMAPPED = 0xFFFF


def parse_csa(data: bytes) -> dict:
    if len(data) != SIZE:
        raise ValueError(f"CSA must be {SIZE} bytes, got {len(data)}")
    if data[:4] != MAGIC:
        raise ValueError(f"not CSA: magic={data[:4].hex()}")
    header_field = struct.unpack(">I", data[4:8])[0]
    mapping = list(struct.unpack(">128H", data[8:]))
    return {"header_field": header_field, "mapping": mapping}


def encode_csa(header_field: int, mapping: list[int]) -> bytes:
    if len(mapping) != ENTRY_COUNT:
        raise ValueError("CSA mapping must contain exactly 128 entries")
    if not 0 <= header_field <= 0xFFFFFFFF:
        raise ValueError("header_field out of range")
    if any(not 0 <= x <= 0xFFFF for x in mapping):
        raise ValueError("mapping entry out of u16 range")
    return MAGIC + struct.pack(">I", header_field) + struct.pack(">128H", *mapping)


def rows(parsed: dict) -> list[dict]:
    out = []
    for code, glyph in enumerate(parsed["mapping"]):
        out.append({
            "code": code,
            "hex": f"0x{code:02X}",
            "char": chr(code) if 0x20 <= code <= 0x7E else None,
            "mapped": glyph != UNMAPPED,
            "glyph_index": None if glyph == UNMAPPED else glyph,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--mapped-only", action="store_true")
    args = ap.parse_args()

    parsed = parse_csa(args.file.read_bytes())
    data_rows = rows(parsed)
    if args.mapped_only:
        data_rows = [r for r in data_rows if r["mapped"]]

    print(json.dumps({
        "file": str(args.file),
        "size": SIZE,
        "header_field": parsed["header_field"],
        "mapped_count": sum(v != UNMAPPED for v in parsed["mapping"]),
        "rows": data_rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
