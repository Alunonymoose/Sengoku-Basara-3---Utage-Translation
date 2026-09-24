#!/usr/bin/env python3
"""
BASARA Foundry PSL geometry census.

READ-ONLY. Mirrors the fixture-proven fields exposed by UtagePslReader:
- PSL header 0x10
- big-endian u16 record count at +0x0C
- 0xB0-byte records
- parent index at +0x38 (0xFFFFFFFF = root)
- node binding id at +0x50
- destination rect +0x74..+0x80
- source rect +0x84..+0x90
- conservative SysRoot/string inventory

This tool does NOT infer which GSM/FIM row a PSL node consumes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import Any

EXPECTED_SAFE_ARC_SHA256 = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"
HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
SCHEMA = "BASARA_FOUNDRY_LAYOUT_CENSUS_V1"

HEADER_SIZE = 0x10
RECORD_SIZE = 0xB0
MAGIC = b"\0PSL"
SYSROOT = b"SysRoot\0"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def require_safe_arc():
    if not SAFE_ARC_PATH.is_file():
        raise RuntimeError(f"missing safe_arc.py: {SAFE_ARC_PATH}")
    actual = hashlib.sha256(SAFE_ARC_PATH.read_bytes()).hexdigest()
    if actual != EXPECTED_SAFE_ARC_SHA256:
        raise RuntimeError(f"safe_arc hash drift expected={EXPECTED_SAFE_ARC_SHA256} actual={actual}")
    return load_module("basara_layout_safe_arc", SAFE_ARC_PATH)


def u16(raw: bytes, off: int) -> int:
    return struct.unpack_from(">H", raw, off)[0]


def u32(raw: bytes, off: int) -> int:
    return struct.unpack_from(">I", raw, off)[0]


def f32(raw: bytes, off: int) -> float:
    return struct.unpack_from(">f", raw, off)[0]


def locate_string_table(raw: bytes, records_end: int) -> int | None:
    for payload_off in range(records_end + 8, len(raw) - len(SYSROOT) + 1):
        if raw[payload_off:payload_off + len(SYSROOT)] != SYSROOT:
            continue
        length_off = payload_off - 4
        if length_off < records_end or u32(raw, length_off) != len(SYSROOT):
            continue
        table_off = length_off - 4
        if table_off < records_end:
            continue
        count = u32(raw, table_off)
        if 0 < count <= 0x10000:
            return table_off
    return None


def extract_ascii_strings(raw: bytes, start: int) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for off in range(start, len(raw) - 4):
        length = u32(raw, off)
        if length < 1 or length > 0x400 or off + 4 + length > len(raw):
            continue
        payload = raw[off + 4:off + 4 + length]
        if not payload or payload[-1] != 0:
            continue
        text = payload[:-1]
        if not text or any(b < 0x20 or b > 0x7E for b in text):
            continue
        value = text.decode("ascii")
        key = (off, value)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "length_prefix_offset": off,
            "payload_offset": off + 4,
            "value": value,
        })
    return out


def parse_psl(raw: bytes) -> dict[str, Any]:
    if len(raw) < HEADER_SIZE or raw[:4] != MAGIC:
        raise ValueError("not a PSL layout")
    version = u32(raw, 4)
    header_word_08 = u32(raw, 8)
    record_count = u16(raw, 12)
    secondary_header_count = u16(raw, 14)
    records_end = HEADER_SIZE + record_count * RECORD_SIZE
    if records_end > len(raw):
        raise ValueError(
            f"record array overruns resource: count={record_count} end=0x{records_end:X} len=0x{len(raw):X}"
        )

    records = []
    roots = 0
    for index in range(record_count):
        off = HEADER_SIZE + index * RECORD_SIZE
        parent_raw = u32(raw, off + 0x38)
        if parent_raw == 0xFFFFFFFF:
            parent = None
            roots += 1
        elif parent_raw >= record_count:
            raise ValueError(f"parent index {parent_raw} outside record count {record_count}")
        else:
            parent = parent_raw

        dx0 = f32(raw, off + 0x74)
        dy0 = f32(raw, off + 0x78)
        dx1 = f32(raw, off + 0x7C)
        dy1 = f32(raw, off + 0x80)
        sx0 = f32(raw, off + 0x84)
        sy0 = f32(raw, off + 0x88)
        sx1 = f32(raw, off + 0x8C)
        sy1 = f32(raw, off + 0x90)

        records.append({
            "record_index": index,
            "record_offset": off,
            "x": f32(raw, off),
            "y": f32(raw, off + 4),
            "parent_record_index": parent,
            "node_binding_id": u32(raw, off + 0x50),
            "destination_x0": dx0,
            "destination_y0": dy0,
            "destination_x1": dx1,
            "destination_y1": dy1,
            "destination_width": dx1 - dx0,
            "destination_height": dy1 - dy0,
            "source_x0": sx0,
            "source_y0": sy0,
            "source_x1": sx1,
            "source_y1": sy1,
            "source_width": sx1 - sx0,
            "source_height": sy1 - sy0,
            "words_70_to_90": [u32(raw, off + 0x70 + i * 4) for i in range(9)],
            "words_94_to_a0": [u32(raw, off + 0x94 + i * 4) for i in range(4)],
        })

    string_table = locate_string_table(raw, records_end)
    strings = extract_ascii_strings(raw, string_table + 4) if string_table is not None else []

    return {
        "version": f"0x{version:X}",
        "header_word_08": header_word_08,
        "record_count": record_count,
        "secondary_header_count": secondary_header_count,
        "records_end": records_end,
        "root_record_count": roots,
        "string_table_offset": string_table,
        "string_table_entry_count": u32(raw, string_table) if string_table is not None else None,
        "strings": strings,
        "records": records,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Utage PSL layout geometry census")
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ns = ap.parse_args()

    root = ns.root.resolve()
    out = ns.out.resolve()
    if not root.is_dir():
        return 3
    out.mkdir(parents=True, exist_ok=True)

    try:
        safe_arc = require_safe_arc()
    except Exception as exc:
        print(f"dependency failure: {exc}", file=sys.stderr)
        return 2

    layouts = []
    nodes = []
    strings = []
    unresolved = []

    for arc in sorted(root.rglob("*.arc")):
        rel = arc.relative_to(root).as_posix()
        try:
            entries = safe_arc.parse_arc(arc.read_bytes())
        except Exception as exc:
            unresolved.append({
                "category": "LAYOUT_ARC_PARSE",
                "owner_path": rel,
                "reason": repr(exc),
                "release_severity": "BLOCKED",
            })
            continue

        for e in entries:
            raw = e["raw"]
            if len(raw) < 4 or raw[:4] != MAGIC:
                continue
            owner = f"{rel}::{e['index']}::{e['name']}"
            try:
                psl = parse_psl(raw)
                layout_id = hashlib.sha256(
                    (rel + "\0" + str(e["index"]) + "\0" + e["name"] + "\0" + sha256(raw)).encode("utf-8")
                ).hexdigest()

                layouts.append({
                    "layout_id": layout_id,
                    "arc_relative_path": rel,
                    "member_index": e["index"],
                    "resource_name": e["name"],
                    "raw_sha256": sha256(raw),
                    "version": psl["version"],
                    "header_word_08": psl["header_word_08"],
                    "record_count": psl["record_count"],
                    "secondary_header_count": psl["secondary_header_count"],
                    "root_record_count": psl["root_record_count"],
                    "records_end": psl["records_end"],
                    "string_table_offset": psl["string_table_offset"],
                    "string_table_entry_count": psl["string_table_entry_count"],
                    "string_inventory_count": len(psl["strings"]),
                })

                for node in psl["records"]:
                    nodes.append({
                        "layout_id": layout_id,
                        "arc_relative_path": rel,
                        "resource_name": e["name"],
                        **node,
                    })
                for st in psl["strings"]:
                    strings.append({
                        "layout_id": layout_id,
                        "arc_relative_path": rel,
                        "resource_name": e["name"],
                        **st,
                    })

                if psl["record_count"] and psl["root_record_count"] != 1:
                    unresolved.append({
                        "category": "LAYOUT_ROOT_COUNT",
                        "owner_path": owner,
                        "reason": f"record_count={psl['record_count']} root_record_count={psl['root_record_count']}",
                        "release_severity": "NEEDS_REVIEW",
                    })
            except Exception as exc:
                unresolved.append({
                    "category": "LAYOUT_PARSE",
                    "owner_path": owner,
                    "reason": repr(exc),
                    "release_severity": "BLOCKED",
                })

    summary = {
        "schema": SCHEMA,
        "layout_count": len(layouts),
        "node_count": len(nodes),
        "string_inventory_count": len(strings),
        "unresolved_count": len(unresolved),
        "important_limit": (
            "Destination/source rectangles are fixture-proven read-only geometry. "
            "This census does not infer which GSM/FIM row or text widget a node consumes."
        ),
    }

    (out / "LAYOUT_CENSUS.json").write_text(
        json.dumps({
            "summary": summary,
            "layouts": layouts,
            "nodes": nodes,
            "strings": strings,
            "unresolved": unresolved,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    fields = [
        "layout_id", "arc_relative_path", "resource_name", "record_index",
        "parent_record_index", "node_binding_id",
        "destination_x0", "destination_y0", "destination_x1", "destination_y1",
        "destination_width", "destination_height",
        "source_x0", "source_y0", "source_x1", "source_y1",
        "source_width", "source_height",
    ]
    with (out / "LAYOUT_NODES.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(nodes)

    print(json.dumps(summary, indent=2))
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
