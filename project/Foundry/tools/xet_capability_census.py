#!/usr/bin/env python3
"""
Read-only ARC/XET capability census for Sengoku BASARA 3 Utage PS3 trees.

Purpose:
  Quantify which real XET instances Foundry can currently decode/write and
  which are blocked by format ambiguity, non-zero swizzle, mip chains, or
  trailing texture data. This tool never modifies an ARC.

Outputs:
  <prefix>.instances.csv
  <prefix>.summary.json

Usage:
  python xet_capability_census.py --root "E:\\Utage Patching New\\PS3_GAME\\USRDIR\\nativePS3\\rom" \
      --out-prefix "E:\\Utage Patching New\\_XET_CAPABILITY\\utage"

ARC v8 and XET bitfield rules are project-canon values. Unknown/special
resources fail closed and are reported rather than guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib
from collections import Counter

ARC_MAGIC = b"\x00CRA"
XET_MAGIC = b"\x00XET"
ARC_ENTRY_SIZE = 80
ARC_TABLE_OFFSET = 8
XET_TYPE_HASH = 0x241F5DEB

# Read mappings supported by current Foundry branch.
FORMAT_STORAGE = {
    0x13: ("BC1", 8),
    0x14: ("BC1", 8),
    # 0x15 intentionally absent: project evidence remains BC2/BC3 ambiguous.
    0x17: ("BC3", 16),
    0x18: ("BC3", 16),
    0x19: ("BC1", 8),
    0x2A: ("BC3", 16),
    0x2B: ("BC3", 16),
}

PLAIN_WRITE_FORMATS = {0x17, 0x18}
YCBCR_WRITE_FORMATS = {0x2A}


def be16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def be32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def decode_member(stored: bytes, raw_size: int) -> tuple[bytes | None, str]:
    if raw_size == 0:
        return b"", "zero_raw_size"

    # ARC v8 commonly stores zlib streams. Try that first even if compressed
    # and raw sizes happen to match numerically.
    try:
        raw = zlib.decompress(stored)
        if len(raw) != raw_size:
            return None, f"zlib_size_mismatch:{len(raw)}!={raw_size}"
        return raw, "zlib"
    except zlib.error:
        if len(stored) == raw_size:
            return stored, "raw"
        return None, "decode_failed"


def parse_xet(raw: bytes) -> dict:
    if len(raw) < 20 or raw[:4] != XET_MAGIC:
        raise ValueError("not_xet_or_truncated")

    w4 = be32(raw, 4)
    w8 = be32(raw, 8)
    wc = be32(raw, 12)
    texture_offset = be32(raw, 16)

    info = {
        "version": w4 & 0xFFF,
        "swizzle": (w4 >> 12) & 0xFFF,
        "reserved": (w4 >> 24) & 0xF,
        "alpha_flags": (w4 >> 28) & 0xF,
        "mip_count": w8 & 0x3F,
        "width": (w8 >> 6) & 0x1FFF,
        "height": (w8 >> 19) & 0x1FFF,
        "image_count": wc & 0xFF,
        "format_code": (wc >> 8) & 0xFF,
        "unknown3": (wc >> 16) & 0xFFFF,
        "texture_offset": texture_offset,
        "raw_length": len(raw),
    }

    fmt = info["format_code"]
    storage = FORMAT_STORAGE.get(fmt)
    info["storage_format"] = storage[0] if storage else ""
    info["block_bytes"] = storage[1] if storage else None

    top_level_size = None
    expected_end = None
    if storage and info["width"] > 0 and info["height"] > 0:
        bw = max(1, (info["width"] + 3) // 4)
        bh = max(1, (info["height"] + 3) // 4)
        top_level_size = bw * bh * storage[1]
        expected_end = texture_offset + top_level_size

    info["top_level_size"] = top_level_size
    info["expected_single_level_end"] = expected_end
    info["has_extra_after_top_level"] = (
        expected_end is not None and len(raw) > expected_end
    )
    info["top_level_overrun"] = (
        expected_end is not None and expected_end > len(raw)
    )

    blockers: list[str] = []
    if info["width"] <= 0 or info["height"] <= 0:
        blockers.append("invalid_dimensions")
    if texture_offset < 20 or texture_offset > len(raw):
        blockers.append("invalid_texture_offset")
    if info["swizzle"] != 0:
        blockers.append("nonzero_swizzle")
    if info["mip_count"] != 1:
        blockers.append("mip_count_not_1")
    if fmt == 0x15:
        blockers.append("ambiguous_format_0x15")
    elif storage is None:
        blockers.append("unsupported_format")
    if info["top_level_overrun"]:
        blockers.append("top_level_overrun")
    if (
        info["mip_count"] == 1
        and info["has_extra_after_top_level"]
        and not info["top_level_overrun"]
    ):
        blockers.append("trailing_texture_data")

    decode_capable = (
        not any(
            b in blockers
            for b in (
                "invalid_dimensions",
                "invalid_texture_offset",
                "nonzero_swizzle",
                "ambiguous_format_0x15",
                "unsupported_format",
                "top_level_overrun",
            )
        )
    )

    write_mode = "none"
    if not blockers:
        if fmt in PLAIN_WRITE_FORMATS:
            write_mode = "plain_bc3"
        elif fmt in YCBCR_WRITE_FORMATS:
            write_mode = "ycbcr_0x2a"
        elif fmt == 0x2B:
            blockers.append("0x2b_write_uncertified")
        elif storage and storage[0] == "BC1":
            blockers.append("bc1_write_uncertified")
        else:
            blockers.append("write_uncertified")
    elif fmt == 0x2B and "0x2b_write_uncertified" not in blockers:
        blockers.append("0x2b_write_uncertified")

    info["decode_capable"] = decode_capable
    info["write_mode"] = write_mode
    info["write_capable"] = write_mode != "none"
    info["blockers"] = blockers
    return info


def iter_arc_entries(path: Path):
    data = path.read_bytes()
    if len(data) < 8 or data[:4] != ARC_MAGIC:
        raise ValueError("not_arc_v8")
    version = be16(data, 4)
    count = be16(data, 6)
    if version != 8:
        raise ValueError(f"unsupported_arc_version:{version}")

    table_end = ARC_TABLE_OFFSET + count * ARC_ENTRY_SIZE
    if table_end > len(data):
        raise ValueError("arc_table_overrun")

    for i in range(count):
        off = ARC_TABLE_OFFSET + i * ARC_ENTRY_SIZE
        entry = data[off : off + ARC_ENTRY_SIZE]
        name = entry[:64].split(b"\x00", 1)[0].decode("ascii", "replace")
        type_hash = be32(entry, 64)
        comp_size = be32(entry, 68)
        packed = be32(entry, 72)
        data_offset = be32(entry, 76)
        raw_size = packed >> 3
        flags = packed & 7

        end = data_offset + comp_size
        if data_offset > len(data) or end > len(data):
            yield {
                "entry_index": i,
                "name": name,
                "type_hash": type_hash,
                "flags": flags,
                "raw_size": raw_size,
                "comp_size": comp_size,
                "error": "entry_payload_overrun",
            }, None
            continue

        meta = {
            "entry_index": i,
            "name": name,
            "type_hash": type_hash,
            "flags": flags,
            "raw_size": raw_size,
            "comp_size": comp_size,
            "error": "",
        }
        yield meta, data[data_offset:end]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--out-prefix", required=True, type=Path)
    ap.add_argument(
        "--all-xet-magic",
        action="store_true",
        help="inspect every decoded member for XET magic instead of only type hash 0x241F5DEB",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    prefix = args.out_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)

    arc_paths = sorted(root.rglob("*.arc"))
    rows: list[dict] = []
    arc_errors: list[dict] = []
    total_entries = 0
    texture_entries = 0

    for arc_no, arc_path in enumerate(arc_paths, 1):
        rel = arc_path.relative_to(root).as_posix()
        try:
            entries = iter_arc_entries(arc_path)
            for meta, stored in entries:
                total_entries += 1
                if stored is None:
                    if meta["type_hash"] == XET_TYPE_HASH:
                        rows.append({
                            "archive": rel,
                            **meta,
                            "member_decode": "",
                            "resource_sha256": "",
                            "xet_error": meta["error"],
                        })
                    continue

                if not args.all_xet_magic and meta["type_hash"] != XET_TYPE_HASH:
                    continue

                raw, member_decode = decode_member(stored, meta["raw_size"])
                if raw is None:
                    if meta["type_hash"] == XET_TYPE_HASH:
                        rows.append({
                            "archive": rel,
                            **meta,
                            "member_decode": member_decode,
                            "resource_sha256": "",
                            "xet_error": member_decode,
                        })
                    continue

                is_xet = raw.startswith(XET_MAGIC)
                if not is_xet:
                    if meta["type_hash"] == XET_TYPE_HASH:
                        rows.append({
                            "archive": rel,
                            **meta,
                            "member_decode": member_decode,
                            "resource_sha256": hashlib.sha256(raw).hexdigest(),
                            "xet_error": "texture_type_without_xet_magic",
                        })
                    continue

                texture_entries += 1
                try:
                    info = parse_xet(raw)
                    row = {
                        "archive": rel,
                        **meta,
                        "member_decode": member_decode,
                        "resource_sha256": hashlib.sha256(raw).hexdigest(),
                        "xet_error": "",
                        **info,
                    }
                    row["blockers"] = ";".join(info["blockers"])
                    rows.append(row)
                except Exception as exc:
                    rows.append({
                        "archive": rel,
                        **meta,
                        "member_decode": member_decode,
                        "resource_sha256": hashlib.sha256(raw).hexdigest(),
                        "xet_error": f"{type(exc).__name__}:{exc}",
                    })
        except Exception as exc:
            arc_errors.append({"archive": rel, "error": f"{type(exc).__name__}:{exc}"})

        if arc_no % 250 == 0 or arc_no == len(arc_paths):
            print(f"[{arc_no}/{len(arc_paths)}] ARCs; {texture_entries} XET instances", file=sys.stderr)

    fieldnames = [
        "archive", "entry_index", "name", "type_hash", "flags",
        "raw_size", "comp_size", "member_decode", "resource_sha256",
        "version", "swizzle", "reserved", "alpha_flags", "mip_count",
        "width", "height", "image_count", "format_code", "unknown3",
        "texture_offset", "raw_length", "storage_format", "block_bytes",
        "top_level_size", "expected_single_level_end",
        "has_extra_after_top_level", "top_level_overrun",
        "decode_capable", "write_capable", "write_mode", "blockers",
        "xet_error",
    ]

    csv_path = prefix.with_suffix(".instances.csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    fmt_counts = Counter()
    swizzle_counts = Counter()
    mip_counts = Counter()
    write_modes = Counter()
    blocker_counts = Counter()
    unique_payloads = set()
    unique_paths = set()
    valid_rows = 0

    for row in rows:
        if row.get("format_code") is None:
            continue
        valid_rows += 1
        fmt_counts[f"0x{int(row['format_code']):02X}"] += 1
        swizzle_counts[str(row.get("swizzle"))] += 1
        mip_counts[str(row.get("mip_count"))] += 1
        write_modes[str(row.get("write_mode"))] += 1
        for blocker in str(row.get("blockers") or "").split(";"):
            if blocker:
                blocker_counts[blocker] += 1
        if row.get("resource_sha256"):
            unique_payloads.add(row["resource_sha256"])
        if row.get("name"):
            unique_paths.add((row.get("type_hash"), row["name"]))

    summary = {
        "root": str(root),
        "arc_files_scanned": len(arc_paths),
        "arc_parse_errors": arc_errors,
        "arc_entries_seen": total_entries,
        "xet_instances_parsed": valid_rows,
        "xet_unique_payload_hashes": len(unique_payloads),
        "xet_unique_logical_paths": len(unique_paths),
        "format_counts": dict(sorted(fmt_counts.items())),
        "swizzle_counts": dict(sorted(swizzle_counts.items())),
        "mip_count_counts": dict(sorted(mip_counts.items())),
        "write_mode_counts": dict(sorted(write_modes.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "current_foundry_contract": {
            "plain_bc3_write": ["0x17", "0x18"],
            "dedicated_ycbcr_write": ["0x2A"],
            "display_ycbcr_read": ["0x2A", "0x2B"],
            "write_fail_closed": [
                "0x2B pending real Utage fixture",
                "0x15 BC2/BC3 ambiguity",
                "non-zero swizzle",
                "mip count != 1",
                "single-level trailing texture data",
                "BC1 production writes",
                "unknown formats",
            ],
        },
    }

    json_path = prefix.with_suffix(".summary.json")
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "csv": str(csv_path),
        "summary": str(json_path),
        "arc_files": len(arc_paths),
        "xet_instances": valid_rows,
        "arc_errors": len(arc_errors),
        "write_modes": summary["write_mode_counts"],
        "blockers": summary["blocker_counts"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
