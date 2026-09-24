#!/usr/bin/env python3
"""
BASARA Foundry TNF/CSA font-contract census.

READ-ONLY. Parses real ARC members via canonical safe_arc.py, discovers paired
\0TNF + \0CSA resources by exact internal resource name, validates the mapping,
and exports ASCII advance metrics.

This tool measures the active font contract. It does NOT recommend rewriting
TNF metrics and it does NOT infer widget/panel capacity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import statistics
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EXPECTED_SAFE_ARC_SHA256 = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"

SCHEMA = "BASARA_FOUNDRY_FONT_CONTRACT_CENSUS_V1"


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


def require_safe_arc() -> Any:
    if not SAFE_ARC_PATH.is_file():
        raise RuntimeError(f"missing canonical safe_arc.py: {SAFE_ARC_PATH}")
    actual = hashlib.sha256(SAFE_ARC_PATH.read_bytes()).hexdigest()
    if actual != EXPECTED_SAFE_ARC_SHA256:
        raise RuntimeError(
            f"safe_arc hash drift: expected={EXPECTED_SAFE_ARC_SHA256} actual={actual}"
        )
    return load_module("basara_font_safe_arc", SAFE_ARC_PATH)


def parse_tnf(raw: bytes) -> dict[str, Any]:
    if len(raw) < 32 or raw[:4] != b"\0TNF":
        raise ValueError("not a TNF resource")
    count = struct.unpack_from(">I", raw, 8)[0]
    cell_w = struct.unpack_from(">I", raw, 12)[0]
    cell_h = struct.unpack_from(">I", raw, 16)[0]
    end = 32 + count * 8
    if count > 1_000_000 or end > len(raw):
        raise ValueError(f"TNF record table exceeds resource: count={count} len={len(raw)}")
    records = []
    for i in range(count):
        glyph_id, atlas_x, atlas_y, advance = struct.unpack_from(">4H", raw, 32 + i * 8)
        records.append({
            "index": i,
            "glyph_id": glyph_id,
            "atlas_x": atlas_x,
            "atlas_y": atlas_y,
            "advance": advance,
        })
    return {
        "count": count,
        "cell_width": cell_w,
        "cell_height": cell_h,
        "records": records,
        "trailing_bytes": len(raw) - end,
    }


def parse_csa(raw: bytes) -> dict[str, Any]:
    if len(raw) < 8 or raw[:4] != b"\0CSA":
        raise ValueError("not a CSA resource")
    payload = raw[8:]
    if len(payload) % 2:
        raise ValueError("CSA mapping payload is not u16-aligned")
    mapping = list(struct.unpack(">" + "H" * (len(payload) // 2), payload))
    return {
        "mapping_count": len(mapping),
        "mapping": mapping,
    }


def ascii_contract(tnf: dict[str, Any], csa: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    mapping = csa["mapping"]
    records = tnf["records"]
    for cp in range(32, 127):
        idx = mapping[cp] if cp < len(mapping) else None
        row = {
            "codepoint": cp,
            "char": chr(cp),
            "tnf_index": idx,
            "advance": None,
            "glyph_id": None,
            "atlas_x": None,
            "atlas_y": None,
            "status": None,
        }
        if idx is None:
            row["status"] = "CSA_OUT_OF_RANGE"
            issues.append(f"U+{cp:04X}: CSA table has no entry")
        elif idx == 0xFFFF:
            row["status"] = "UNMAPPED"
        elif idx >= len(records):
            row["status"] = "INVALID_TNF_INDEX"
            issues.append(f"U+{cp:04X}: CSA index {idx} >= TNF count {len(records)}")
        else:
            rec = records[idx]
            row.update({
                "advance": rec["advance"],
                "glyph_id": rec["glyph_id"],
                "atlas_x": rec["atlas_x"],
                "atlas_y": rec["atlas_y"],
                "status": "OK",
            })
        rows.append(row)
    return rows, issues


def classify_latin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    printable = [r for r in rows if r["status"] == "OK" and r["char"] != " "]
    advances = [int(r["advance"]) for r in printable]
    if not advances:
        return {
            "mapped_printable_ascii": 0,
            "unique_advances": [],
            "min_advance": None,
            "max_advance": None,
            "median_advance": None,
            "mean_advance": None,
            "width_model": "UNKNOWN",
        }
    unique = sorted(set(advances))
    dominant_count = max(advances.count(v) for v in unique)
    ratio = dominant_count / len(advances)
    if len(unique) == 1 or ratio >= 0.85:
        model = "FIXED_OR_NEAR_FIXED"
    elif len(unique) >= 5:
        model = "PROPORTIONAL"
    else:
        model = "MIXED"
    return {
        "mapped_printable_ascii": len(advances),
        "unique_advances": unique,
        "min_advance": min(advances),
        "max_advance": max(advances),
        "median_advance": statistics.median(advances),
        "mean_advance": round(statistics.fmean(advances), 4),
        "dominant_advance_ratio": round(ratio, 4),
        "width_model": model,
    }


def measure_ascii(text: str, ascii_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cp = {r["codepoint"]: r for r in ascii_rows}
    total = 0
    missing = []
    per_char = []
    for ch in text:
        cp = ord(ch)
        row = by_cp.get(cp)
        if row is None or row.get("status") != "OK":
            missing.append({"char": ch, "codepoint": cp})
            per_char.append({"char": ch, "advance": None})
            continue
        adv = int(row["advance"])
        total += adv
        per_char.append({"char": ch, "advance": adv})
    return {
        "text": text,
        "advance_units": total if not missing else None,
        "missing": missing,
        "per_char": per_char,
    }


def scan_root(root: Path, safe_arc) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    contracts = []
    ascii_rows_all = []
    unresolved = []

    for arc in sorted(root.rglob("*.arc")):
        rel = arc.relative_to(root).as_posix()
        try:
            entries = safe_arc.parse_arc(arc.read_bytes())
        except Exception as exc:
            unresolved.append({
                "category": "FONT_ARC_PARSE",
                "owner_path": rel,
                "reason": repr(exc),
                "release_severity": "BLOCKED",
            })
            continue

        by_name: dict[str, dict[bytes, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for e in entries:
            raw = e["raw"]
            if len(raw) >= 4 and raw[:4] in {b"\0TNF", b"\0CSA"}:
                by_name[e["name"]][raw[:4]].append(e)

        for name, kinds in by_name.items():
            tnfs = kinds.get(b"\0TNF", [])
            csas = kinds.get(b"\0CSA", [])
            owner = f"{rel}::{name}"

            if len(tnfs) != 1 or len(csas) != 1:
                unresolved.append({
                    "category": "FONT_PAIRING",
                    "owner_path": owner,
                    "reason": f"expected exactly one TNF + one CSA with same internal name; TNF={len(tnfs)} CSA={len(csas)}",
                    "release_severity": "NEEDS_REVIEW",
                })
                continue

            try:
                tnf = parse_tnf(tnfs[0]["raw"])
                csa = parse_csa(csas[0]["raw"])
                ascii_rows, issues = ascii_contract(tnf, csa)
                summary = classify_latin(ascii_rows)
                contract_id = hashlib.sha256(
                    (rel + "\0" + name + "\0" + sha256(tnfs[0]["raw"]) + "\0" + sha256(csas[0]["raw"])).encode("utf-8")
                ).hexdigest()
                contracts.append({
                    "contract_id": contract_id,
                    "arc_relative_path": rel,
                    "resource_name": name,
                    "tnf_member_index": tnfs[0]["index"],
                    "csa_member_index": csas[0]["index"],
                    "tnf_sha256": sha256(tnfs[0]["raw"]),
                    "csa_sha256": sha256(csas[0]["raw"]),
                    "tnf_glyph_count": tnf["count"],
                    "tnf_cell_width": tnf["cell_width"],
                    "tnf_cell_height": tnf["cell_height"],
                    "csa_mapping_count": csa["mapping_count"],
                    "tnf_trailing_bytes": tnf["trailing_bytes"],
                    "validation_issue_count": len(issues),
                    **summary,
                })
                for r in ascii_rows:
                    ascii_rows_all.append({
                        "contract_id": contract_id,
                        "arc_relative_path": rel,
                        "resource_name": name,
                        **r,
                    })
                for issue in issues:
                    unresolved.append({
                        "category": "FONT_MAPPING",
                        "owner_path": owner,
                        "reason": issue,
                        "release_severity": "BLOCKED",
                    })
            except Exception as exc:
                unresolved.append({
                    "category": "FONT_PARSE",
                    "owner_path": owner,
                    "reason": repr(exc),
                    "release_severity": "BLOCKED",
                })

    return contracts, ascii_rows_all, unresolved


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Utage TNF/CSA font-contract census")
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--measure", action="append", default=[],
                    help="Optional ASCII text to measure under every discovered contract.")
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

    contracts, ascii_rows, unresolved = scan_root(root, safe_arc)
    rows_by_contract: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ascii_rows:
        rows_by_contract[row["contract_id"]].append(row)

    measurements = []
    for contract in contracts:
        rows = rows_by_contract[contract["contract_id"]]
        for sample in ns.measure:
            measurements.append({
                "contract_id": contract["contract_id"],
                "arc_relative_path": contract["arc_relative_path"],
                "resource_name": contract["resource_name"],
                **measure_ascii(sample, rows),
            })

    summary = {
        "schema": SCHEMA,
        "font_contract_count": len(contracts),
        "fixed_or_near_fixed": sum(c["width_model"] == "FIXED_OR_NEAR_FIXED" for c in contracts),
        "proportional": sum(c["width_model"] == "PROPORTIONAL" for c in contracts),
        "mixed": sum(c["width_model"] == "MIXED" for c in contracts),
        "unknown": sum(c["width_model"] == "UNKNOWN" for c in contracts),
        "unresolved_count": len(unresolved),
        "important_limit": (
            "TNF/CSA advances measure font width only. They do not establish the active widget's usable width, "
            "margins, scale, line limit, or runtime ownership. Do not rewrite TNF to fix a layout overflow without separate evidence."
        ),
    }
    payload = {
        "summary": summary,
        "contracts": contracts,
        "ascii_mappings": ascii_rows,
        "measurements": measurements,
        "unresolved": unresolved,
    }
    (out / "FONT_CONTRACT_CENSUS.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    contract_fields = [
        "contract_id", "arc_relative_path", "resource_name",
        "tnf_member_index", "csa_member_index", "tnf_sha256", "csa_sha256",
        "tnf_glyph_count", "tnf_cell_width", "tnf_cell_height", "csa_mapping_count",
        "mapped_printable_ascii", "unique_advances", "min_advance", "max_advance",
        "median_advance", "mean_advance", "dominant_advance_ratio", "width_model",
        "validation_issue_count",
    ]
    with (out / "FONT_CONTRACT_CENSUS.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=contract_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(contracts)

    print(json.dumps(summary, indent=2))
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
