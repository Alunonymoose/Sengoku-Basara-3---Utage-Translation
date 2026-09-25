#!/usr/bin/env python3
"""Inspect Utage PS3 ARC v8 rArchive/SCRA child manifests.

Public-safe utility: it requires the researcher to supply their own ARC files.
"""

from __future__ import annotations
import argparse
import json
import struct
import zlib
from pathlib import Path

RARCHIVE = 0x73850D05

def path_hash(path: str) -> int:
    return (~zlib.crc32(path.lower().encode("utf-8"))) & 0xFFFFFFFF

def read_arc(path: Path, with_payload: bool = False):
    blob = path.read_bytes()
    if blob[:4] != b"\x00CRA":
        raise ValueError(f"{path}: expected PS3 big-endian \\0CRA")
    version, count = struct.unpack(">HH", blob[4:8])
    rows = []
    for index in range(count):
        base = 8 + index * 0x50
        entry = blob[base:base + 0x50]
        if len(entry) != 0x50:
            raise ValueError(f"{path}: truncated ARC table")
        name = entry[:0x40].split(b"\0", 1)[0].decode("latin-1")
        type_hash, comp_size, size_flags, offset = struct.unpack(">IIII", entry[0x40:0x50])
        decomp_size = size_flags >> 3
        flags = size_flags & 7
        payload = None
        if with_payload:
            stored = blob[offset:offset + comp_size]
            payload = stored if comp_size == decomp_size else zlib.decompress(stored)
        rows.append({
            "index": index, "name": name, "type_hash": type_hash,
            "path_hash": path_hash(name), "compressed_size": comp_size,
            "decompressed_size": decomp_size, "flags": flags, "offset": offset,
            "payload": payload,
        })
    return version, rows

def parse_scra(payload: bytes):
    if payload[:4] != b"SCRA" or len(payload) < 8:
        raise ValueError("not an SCRA payload")
    version, count = struct.unpack(">HH", payload[4:8])
    need = 8 + count * 8
    if len(payload) != need:
        raise ValueError(f"SCRA size mismatch: got {len(payload)}, expected {need}")
    pairs = [struct.unpack(">II", payload[8+i*8:16+i*8]) for i in range(count)]
    return version, pairs

def inspect(parent: Path, native_root: Path | None):
    arc_version, rows = read_arc(parent, with_payload=True)
    out = {"parent": str(parent), "arc_version": arc_version, "manifests": []}
    for row in rows:
        payload = row["payload"]
        if row["type_hash"] != RARCHIVE or not payload or payload[:4] != b"SCRA":
            continue
        scra_version, pairs = parse_scra(payload)
        item = {
            "entry_index": row["index"], "child": row["name"],
            "scra_version": scra_version, "pair_count": len(pairs),
            "pairs": [{"type_hash": f"{a:08X}", "path_hash": f"{b:08X}"} for a,b in pairs],
        }
        if native_root is not None:
            child = native_root / (row["name"].replace("\\", "/") + ".arc")
            item["child_path"] = str(child)
            item["child_exists"] = child.is_file()
            if child.is_file():
                child_version, child_rows = read_arc(child, with_payload=False)
                child_pairs = [(x["type_hash"], x["path_hash"]) for x in child_rows]
                item["child_arc_version"] = child_version
                item["child_manifest_exact"] = child_pairs == pairs
        out["manifests"].append(item)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parent_arc", type=Path)
    ap.add_argument("--native-root", type=Path, help="nativePS3 root used to validate SCRA child paths")
    args = ap.parse_args()
    print(json.dumps(inspect(args.parent_arc, args.native_root), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
