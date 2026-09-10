#!/usr/bin/env python3
"""Small MT Framework ARC v8 inspector/rebuilder for the Tenka patch.

The rebuild path preserves archive metadata, entry order, flags, and every
untouched compressed blob. Only explicitly replaced resources are recompressed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


ENTRY_SIZE = 80
TABLE_START = 8


@dataclass
class Entry:
    index: int
    name: str
    type_hash: int
    compressed_size: int
    raw_size: int
    flags: int
    payload_offset: int
    record: bytes
    compressed: bytes


@dataclass
class Archive:
    data: bytes
    endian: str
    magic: bytes
    version: int
    entries: list[Entry]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_name(raw: bytes) -> str:
    raw = raw.split(b"\0", 1)[0]
    for encoding in ("utf-8", "shift_jis", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", errors="replace")


def parse_arc(path: Path) -> Archive:
    data = path.read_bytes()
    if data[:4] == b"\0CRA":
        endian = ">"
    elif data[:4] == b"ARC\0":
        endian = "<"
    else:
        raise ValueError(f"unsupported ARC magic: {data[:4]!r}")
    version, count = struct.unpack_from(endian + "HH", data, 4)
    table_end = TABLE_START + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError("entry table exceeds file")
    entries: list[Entry] = []
    for index in range(count):
        offset = TABLE_START + index * ENTRY_SIZE
        record = data[offset : offset + ENTRY_SIZE]
        type_hash, compressed_size, packed_size, payload_offset = struct.unpack_from(
            endian + "IIII", record, 64
        )
        payload_end = payload_offset + compressed_size
        if payload_offset > len(data) or payload_end > len(data):
            raise ValueError(f"entry {index} payload exceeds file")
        entries.append(
            Entry(
                index=index,
                name=decode_name(record[:64]),
                type_hash=type_hash,
                compressed_size=compressed_size,
                raw_size=packed_size >> 3,
                flags=packed_size & 7,
                payload_offset=payload_offset,
                record=record,
                compressed=data[payload_offset:payload_end],
            )
        )
    return Archive(data, endian, data[:4], version, entries)


def unpack(entry: Entry) -> bytes:
    try:
        return zlib.decompress(entry.compressed)
    except zlib.error:
        if entry.compressed_size == entry.raw_size:
            return entry.compressed
        raise


def entry_json(entry: Entry) -> dict:
    raw = unpack(entry)
    return {
        "index": entry.index,
        "name": entry.name,
        "type_hash": f"0x{entry.type_hash:08X}",
        "compressed_size": entry.compressed_size,
        "raw_size_declared": entry.raw_size,
        "raw_size_actual": len(raw),
        "flags": entry.flags,
        "payload_offset": entry.payload_offset,
        "compressed_sha256": sha256(entry.compressed),
        "raw_sha256": sha256(raw),
    }


def find_entry(arc: Archive, selector: str) -> Entry:
    if selector.isdecimal():
        index = int(selector)
        return arc.entries[index]
    matches = [entry for entry in arc.entries if entry.name == selector]
    if len(matches) != 1:
        raise ValueError(f"selector {selector!r} matched {len(matches)} entries")
    return matches[0]


def inspect_command(args: argparse.Namespace) -> None:
    result = []
    for path in args.arcs:
        arc = parse_arc(path)
        result.append(
            {
                "path": str(path),
                "size": len(arc.data),
                "sha256": sha256(arc.data),
                "magic": arc.magic.hex(),
                "version": arc.version,
                "entry_count": len(arc.entries),
                "table_end": TABLE_START + len(arc.entries) * ENTRY_SIZE,
                "first_payload_offset": min(e.payload_offset for e in arc.entries),
                "entries": [entry_json(e) for e in arc.entries],
            }
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def extract_command(args: argparse.Namespace) -> None:
    arc = parse_arc(args.arc)
    entry = find_entry(arc, args.selector)
    raw = unpack(entry)
    args.output.write_bytes(raw)
    print(json.dumps({**entry_json(entry), "output": str(args.output)}, indent=2))


def detect_alignment(arc: Archive) -> int:
    offsets = sorted({entry.payload_offset for entry in arc.entries})
    for alignment in (2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4):
        if all(offset % alignment == 0 for offset in offsets):
            return alignment
    return 1


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def rebuild(arc: Archive, replacements: dict[int, bytes]) -> bytes:
    alignment = detect_alignment(arc)
    count = len(arc.entries)
    table_end = TABLE_START + count * ENTRY_SIZE
    first_payload = min(entry.payload_offset for entry in arc.entries)
    prefix = bytearray(arc.data[:first_payload])
    new_payloads: list[bytes] = []
    new_raw_sizes: list[int] = []
    for entry in arc.entries:
        if entry.index in replacements:
            raw = replacements[entry.index]
            if entry.compressed_size == entry.raw_size:
                compressed = raw
            else:
                compressed = zlib.compress(raw, 9)
            new_payloads.append(compressed)
            new_raw_sizes.append(len(raw))
        else:
            new_payloads.append(entry.compressed)
            new_raw_sizes.append(entry.raw_size)

    output = prefix
    cursor = first_payload
    new_offsets: list[int] = []
    for payload in new_payloads:
        cursor = align(cursor, alignment)
        if len(output) < cursor:
            output.extend(b"\0" * (cursor - len(output)))
        new_offsets.append(cursor)
        output.extend(payload)
        cursor += len(payload)

    for entry, payload, raw_size, payload_offset in zip(
        arc.entries, new_payloads, new_raw_sizes, new_offsets
    ):
        record_offset = TABLE_START + entry.index * ENTRY_SIZE
        packed_size = (raw_size << 3) | entry.flags
        struct.pack_into(
            arc.endian + "IIII",
            output,
            record_offset + 64,
            entry.type_hash,
            len(payload),
            packed_size,
            payload_offset,
        )
    if len(output) < table_end:
        raise AssertionError("rebuilt archive truncated its entry table")
    return bytes(output)


def replace_command(args: argparse.Namespace) -> None:
    arc = parse_arc(args.arc)
    entry = find_entry(arc, args.selector)
    raw = args.replacement.read_bytes()
    rebuilt = rebuild(arc, {entry.index: raw})
    args.output.write_bytes(rebuilt)
    verification = parse_arc(args.output)
    changed = []
    for old, new in zip(arc.entries, verification.entries):
        if old.compressed != new.compressed:
            changed.append(new.index)
    print(
        json.dumps(
            {
                "input": str(args.arc),
                "output": str(args.output),
                "selector": args.selector,
                "changed_compressed_entries": changed,
                "input_sha256": sha256(arc.data),
                "output_sha256": sha256(rebuilt),
                "alignment": detect_alignment(arc),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("arcs", nargs="+", type=Path)
    inspect_parser.set_defaults(func=inspect_command)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("arc", type=Path)
    extract_parser.add_argument("selector")
    extract_parser.add_argument("output", type=Path)
    extract_parser.set_defaults(func=extract_command)

    replace_parser = subparsers.add_parser("replace")
    replace_parser.add_argument("arc", type=Path)
    replace_parser.add_argument("selector")
    replace_parser.add_argument("replacement", type=Path)
    replace_parser.add_argument("output", type=Path)
    replace_parser.set_defaults(func=replace_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
