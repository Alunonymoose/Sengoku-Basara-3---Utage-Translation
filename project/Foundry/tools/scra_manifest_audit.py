#!/usr/bin/env python3
"""Read-only Utage ARCS/SCRA child-manifest auditor.

Project-authored tool; MIT licensed under the repository LICENSE.

Usage:
    python scra_manifest_audit.py PARENT.arc --native-root /path/to/nativePS3

Without --native-root the tool validates SCRA structure and resolves manifest
pairs against flattened members in PARENT.arc. With --native-root it also
locates each virtual child ARC and compares its ordered member-identity table
and decompressed payloads with the flattened parent resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

ARC_MAGIC_PS3 = b"\x00CRA"
ARCS_MAGIC_PS3 = b"SCRA"
ARC_VERSION = 8
ENTRY_SIZE = 80
RARCHIVE_HASH = 0x73850D05


def path_hash(path: str) -> int:
    """Full 32-bit MT path hash used by ARCS/SCRA (not high-bit masked)."""
    return (~zlib.crc32(path.lower().encode("utf-8"))) & 0xFFFFFFFF


def is_zlib(data: bytes) -> bool:
    if len(data) < 2:
        return False
    cmf, flg = data[0], data[1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and (((cmf << 8) | flg) % 31) == 0
    )


@dataclass(frozen=True)
class ArcEntry:
    index: int
    name: str
    type_hash: int
    stored_size: int
    raw_size: int
    packed_flags: int
    offset: int
    stored: bytes
    raw: bytes

    @property
    def identity(self) -> tuple[int, int]:
        return self.type_hash, path_hash(self.name)


def read_arc(path: Path) -> list[ArcEntry]:
    data = path.read_bytes()
    if len(data) < 8 or data[:4] != ARC_MAGIC_PS3:
        raise ValueError(f"{path}: not a PS3 ARC (expected 00 43 52 41)")
    version, count = struct.unpack_from(">HH", data, 4)
    if version != ARC_VERSION:
        raise ValueError(f"{path}: unsupported ARC version {version}")

    table_end = 8 + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError(f"{path}: truncated ARC table")

    entries: list[ArcEntry] = []
    for i in range(count):
        row = 8 + i * ENTRY_SIZE
        name = data[row : row + 64].split(b"\0", 1)[0].decode("utf-8", "replace")
        type_hash, stored_size, packed, offset = struct.unpack_from(">IIII", data, row + 64)
        raw_size = packed >> 3
        flags = packed & 7
        stored = data[offset : offset + stored_size]
        if len(stored) != stored_size:
            raise ValueError(f"{path}: member {i} payload extends past EOF")
        raw = zlib.decompress(stored) if is_zlib(stored) else stored
        entries.append(
            ArcEntry(i, name, type_hash, stored_size, raw_size, flags, offset, stored, raw)
        )
    return entries


def parse_scra(data: bytes) -> dict:
    if len(data) < 8 or data[:4] != ARCS_MAGIC_PS3:
        raise ValueError("not an ARCS/SCRA payload")
    version, count = struct.unpack_from(">HH", data, 4)
    expected = 8 + count * 8
    if len(data) != expected:
        raise ValueError(f"SCRA length {len(data)} != expected {expected}")
    pairs = [struct.unpack_from(">II", data, 8 + i * 8) for i in range(count)]
    return {"version": version, "count": count, "pairs": pairs}


def virtual_child_path(native_root: Path, manifest_name: str) -> Path:
    parts = manifest_name.replace("/", "\\").split("\\")
    return native_root.joinpath(*parts).with_suffix(".arc")


def audit(parent_path: Path, native_root: Path | None) -> dict:
    parent = read_arc(parent_path)
    identity_map: dict[tuple[int, int], list[ArcEntry]] = {}
    for entry in parent:
        identity_map.setdefault(entry.identity, []).append(entry)

    manifests = []
    totals = {
        "manifest_count": 0,
        "manifest_reference_count": 0,
        "resolved_unique": 0,
        "missing": 0,
        "ambiguous": 0,
        "child_arc_found": 0,
        "child_table_exact": 0,
        "child_raw_payload_equal": 0,
        "child_raw_payload_total": 0,
        "child_stored_payload_equal": 0,
        "child_stored_payload_total": 0,
    }

    for entry in parent:
        if entry.type_hash != RARCHIVE_HASH or entry.raw[:4] != ARCS_MAGIC_PS3:
            continue

        parsed = parse_scra(entry.raw)
        totals["manifest_count"] += 1
        totals["manifest_reference_count"] += parsed["count"]

        refs = []
        for type_hash, name_hash in parsed["pairs"]:
            matches = identity_map.get((type_hash, name_hash), [])
            status = "unique" if len(matches) == 1 else "missing" if not matches else "ambiguous"
            totals[{"unique": "resolved_unique", "missing": "missing", "ambiguous": "ambiguous"}[status]] += 1
            refs.append(
                {
                    "type_hash": f"0x{type_hash:08X}",
                    "path_hash": f"0x{name_hash:08X}",
                    "resolution": status,
                    "parent_member": matches[0].name if len(matches) == 1 else None,
                }
            )

        result = {
            "parent_member_index": entry.index,
            "virtual_child": entry.name,
            "version": parsed["version"],
            "count": parsed["count"],
            "references": refs,
        }

        if native_root is not None:
            child_path = virtual_child_path(native_root, entry.name)
            result["child_path"] = str(child_path)
            result["child_exists"] = child_path.is_file()
            if child_path.is_file():
                totals["child_arc_found"] += 1
                child = read_arc(child_path)
                child_pairs = [x.identity for x in child]
                result["child_table_exact"] = child_pairs == parsed["pairs"]
                if result["child_table_exact"]:
                    totals["child_table_exact"] += 1

                raw_equal = 0
                stored_equal = 0
                comparisons = []
                for child_entry in child:
                    matches = identity_map.get(child_entry.identity, [])
                    if len(matches) != 1:
                        continue
                    parent_entry = matches[0]
                    r_eq = parent_entry.raw == child_entry.raw
                    s_eq = parent_entry.stored == child_entry.stored
                    raw_equal += int(r_eq)
                    stored_equal += int(s_eq)
                    comparisons.append(
                        {
                            "name": child_entry.name,
                            "raw_equal": r_eq,
                            "stored_equal": s_eq,
                            "parent_raw_sha256": hashlib.sha256(parent_entry.raw).hexdigest(),
                            "child_raw_sha256": hashlib.sha256(child_entry.raw).hexdigest(),
                        }
                    )
                totals["child_raw_payload_equal"] += raw_equal
                totals["child_raw_payload_total"] += len(child)
                totals["child_stored_payload_equal"] += stored_equal
                totals["child_stored_payload_total"] += len(child)
                result["payload_comparison"] = {
                    "raw_equal": raw_equal,
                    "raw_total": len(child),
                    "stored_equal": stored_equal,
                    "stored_total": len(child),
                    "members": comparisons,
                }

        manifests.append(result)

    return {
        "parent": str(parent_path),
        "parent_member_count": len(parent),
        "totals": totals,
        "manifests": manifests,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("parent_arc", type=Path)
    ap.add_argument("--native-root", type=Path, default=None)
    ap.add_argument("--summary", action="store_true", help="omit per-manifest detail")
    args = ap.parse_args()

    result = audit(args.parent_arc, args.native_root)
    if args.summary:
        result = {
            "parent": result["parent"],
            "parent_member_count": result["parent_member_count"],
            "totals": result["totals"],
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
