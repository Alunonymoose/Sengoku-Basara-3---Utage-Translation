#!/usr/bin/env python3
"""Validate MT Framework SCRA child-archive manifests.

Usage:
  python scra_validate.py <parent.arc> --native-root <.../nativePS3>

This tool is read-only. It verifies:
- SCRA structure
- referenced child ARC existence
- manifest pair list vs child ARC membership
- optional parent-vs-child payload equality for manifested resources
"""

from __future__ import annotations
import argparse, os, struct, zlib, collections, json

RARCHIVE = 0x73850D05

def path_hash(path: str) -> int:
    return (~zlib.crc32(path.lower().encode("utf-8"))) & 0xFFFFFFFF

def read_arc(path: str, with_payload: bool = False):
    with open(path, "rb") as f:
        h = f.read(8)
        if h[:4] != b"\x00CRA":
            raise ValueError(f"not PS3 big-endian ARC: {path}")
        version, count = struct.unpack(">HH", h[4:8])
        table = f.read(count * 0x50)
        rows = []
        for i in range(count):
            e = table[i*0x50:(i+1)*0x50]
            name = e[:0x40].split(b"\0",1)[0].decode("latin1")
            typ, cs, sf, off = struct.unpack(">IIII", e[0x40:0x50])
            ds = sf >> 3
            data = None
            if with_payload:
                f.seek(off)
                stored = f.read(cs)
                data = stored if cs == ds else zlib.decompress(stored)
            rows.append(dict(index=i,name=name,type_hash=typ,path_hash=path_hash(name),
                             compressed_size=cs,decompressed_size=ds,flags=sf&7,
                             offset=off,data=data))
        return version, rows

def parse_scra(data: bytes):
    if data[:4] != b"SCRA" or len(data) < 8:
        return None
    version, count = struct.unpack(">HH", data[4:8])
    need = 8 + count * 8
    if len(data) != need:
        raise ValueError(f"SCRA length mismatch: got {len(data)}, expected {need}")
    pairs = [struct.unpack(">II", data[8+i*8:16+i*8]) for i in range(count)]
    return version, pairs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parent_arc")
    ap.add_argument("--native-root", required=True)
    ap.add_argument("--compare-payloads", action="store_true")
    args = ap.parse_args()

    pv, parent = read_arc(args.parent_arc, with_payload=True)
    index = collections.defaultdict(list)
    for e in parent:
        index[(e["type_hash"], e["path_hash"])].append(e)

    report = []
    for e in parent:
        if e["type_hash"] != RARCHIVE or e["compressed_size"] != e["decompressed_size"]:
            continue
        parsed = parse_scra(e["data"])
        if parsed is None:
            continue
        sv, pairs = parsed
        child_path = os.path.join(args.native_root, e["name"].replace("\\", os.sep) + ".arc")
        item = dict(parent_member=e["name"], scra_version=sv, pair_count=len(pairs),
                    child_path=child_path, child_exists=os.path.isfile(child_path))
        if not item["child_exists"]:
            item["membership_exact"] = False
            report.append(item)
            continue
        cv, child = read_arc(child_path, with_payload=args.compare_payloads)
        cpairs = [(x["type_hash"], x["path_hash"]) for x in child]
        item["child_arc_version"] = cv
        item["child_member_count"] = len(child)
        item["membership_exact"] = (pairs == cpairs)
        if args.compare_payloads and item["membership_exact"]:
            equal = diff = missing = 0
            cmap = {(x["type_hash"], x["path_hash"]): x for x in child}
            for pair in pairs:
                candidates = index.get(pair, [])
                ce = cmap.get(pair)
                if not candidates or ce is None:
                    missing += 1
                elif any(pe["data"] == ce["data"] for pe in candidates):
                    equal += 1
                else:
                    diff += 1
            item["payload_equal"] = equal
            item["payload_different"] = diff
            item["payload_missing"] = missing
        report.append(item)

    print(json.dumps({"parent": args.parent_arc, "arc_version": pv,
                      "scra_count": len(report), "manifests": report}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
