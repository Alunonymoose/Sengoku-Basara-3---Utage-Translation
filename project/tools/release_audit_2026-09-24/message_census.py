#!/usr/bin/env python3
"""
BASARA Foundry read-only message/GSM/FIM census.
2026-09-24

Uses:
- canonical pinned safe_arc.py for ARC parsing/decompression;
- recovered FIM_CONTRACT_REPAIR.py for GSM/FIM grammar + desired contract;
- recovered SCAN_TEXT_DEFECTS.py only for its proven Latin glyph ordinal decoder.

No game-file writes.
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

EXPECTED_SAFE_ARC_SHA256 = "f25c53e4ad78e18d5785b8aee197725377130ed9f562a9caa1000a1964bde91d"
EXPECTED_FIM_CONTRACT_SHA256 = "2dda5bcbba10d20467fe91ae9a1e3e0bc0422ab4fcb8e4e7cb2a232dca985013"
EXPECTED_TEXT_SCANNER_SHA256 = "bba221464414ceeb40ab5ecd82f417140555832214efb031be7552bec7587c66"

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
PROJECT_DIR = TOOLS_DIR.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
DIALOGUE_DIR = PROJECT_DIR / "dialogue_tools" / "fim_contract_recovery_2026-09-20"
FIM_CONTRACT_PATH = DIALOGUE_DIR / "FIM_CONTRACT_REPAIR.py"
TEXT_SCANNER_PATH = DIALOGUE_DIR / "SCAN_TEXT_DEFECTS.py"

SCHEMA = "BASARA_FOUNDRY_MESSAGE_CENSUS_V1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing dependency: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"dependency hash drift: {path} expected={expected} actual={actual}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def decode_record(seq: list[int], grammar, glyph_decoder) -> dict[str, Any]:
    toks = grammar.tokens(seq)
    pieces: list[str] = []
    stray = []
    controls = []
    lines = [""]
    speech_count = 1

    for offset, value, args in toks:
        if value == 0xFFFE:
            pieces.append("\n")
            lines.append("")
            controls.append({"offset": offset, "control": "0xFFFE", "argc": len(args)-1})
            continue
        if value == 0xFFFD:
            pieces.append(" | ")
            speech_count += 1
            controls.append({"offset": offset, "control": "0xFFFD", "argc": len(args)-1})
            continue
        if value >= 0xF000:
            controls.append({"offset": offset, "control": f"0x{value:04X}", "argc": len(args)-1})
            continue
        if value >= 0x8000:
            stray.append({"offset": offset, "glyph": f"0x{value:04X}", "class": "NON_LATIN_OR_HIGH_GLYPH"})
            pieces.append("�")
            lines[-1] += "�"
            continue

        ch = glyph_decoder.dec(value)
        if ch is None:
            stray.append({"offset": offset, "glyph": f"0x{value:04X}", "class": "UNMAPPED_LATIN_FONT_GLYPH"})
            pieces.append("�")
            lines[-1] += "�"
        else:
            pieces.append(ch)
            lines[-1] += ch

    return {
        "text": "".join(pieces),
        "stray_glyphs": stray,
        "controls": controls,
        "visual_line_count": len(lines),
        "line_lengths_chars": [len(x) for x in lines],
        "heuristic_over_41_chars": any(len(x) > 41 for x in lines),
        "speech_count_from_delimiters": speech_count,
    }


def check_fim_contract(graw: bytes, fraw: bytes, grammar) -> dict[str, Any]:
    want, base = grammar.desired(graw, fraw)
    mismatches = []
    for j, (lines, glyphs, start) in want.items():
        off = base + j * 44
        c0, c1 = struct.unpack_from(">II", fraw, off)
        expected0 = (lines << 16) | glyphs
        actual_start = c1 >> 16
        if c0 != expected0 or actual_start != start:
            mismatches.append({
                "format_index": j,
                "actual_col0": c0,
                "expected_col0": expected0,
                "actual_start": actual_start,
                "expected_start": start,
            })
    return {
        "format_record_count": len(want),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "PASS" if not mismatches else "FAIL",
    }


def scan_arc(path: Path, root: Path, safe_arc, grammar, glyph_decoder):
    data = path.read_bytes()
    entries = safe_arc.parse_arc(data)
    rel = path.relative_to(root).as_posix()
    arc_sha = hashlib.sha256(data).hexdigest()

    by_magic: dict[tuple[str, bytes], dict[str, Any]] = {}
    for e in entries:
        raw = e["raw"]
        if len(raw) >= 4:
            by_magic.setdefault((e["name"], raw[:4]), e)

    rows = []
    resources = []
    findings = []

    for e in entries:
        graw = e["raw"]
        if graw[:4] != b"\0GSM":
            continue
        owner = f"{rel}::{e['index']}::{e['name']}"
        resource = {
            "arc_relative_path": rel,
            "arc_sha256": arc_sha,
            "gsm_member_index": e["index"],
            "resource_name": e["name"],
            "gsm_sha256": hashlib.sha256(graw).hexdigest(),
            "fim_member_index": None,
            "fim_sha256": None,
            "record_count": None,
            "fim_contract_status": "NO_FIM_PAIR",
            "fim_format_record_count": None,
            "fim_mismatch_count": None,
            "parse_status": "PENDING",
        }

        fim_e = by_magic.get((e["name"], b"\0FIM"))
        try:
            recs = grammar.gsm_records(graw)
            resource["record_count"] = len(recs)

            if fim_e is not None:
                fraw = fim_e["raw"]
                resource["fim_member_index"] = fim_e["index"]
                resource["fim_sha256"] = hashlib.sha256(fraw).hexdigest()
                contract = check_fim_contract(graw, fraw, grammar)
                resource["fim_contract_status"] = contract["status"]
                resource["fim_format_record_count"] = contract["format_record_count"]
                resource["fim_mismatch_count"] = contract["mismatch_count"]
                if contract["mismatch_count"]:
                    findings.append({
                        "category": "FIM_CONTRACT_MISMATCH",
                        "owner_path": owner,
                        "count": contract["mismatch_count"],
                        "details": contract["mismatches"][:100],
                        "release_severity": "BLOCKED",
                    })

            stray_total = 0
            heuristic_overlong = 0
            for ri, seq in enumerate(recs):
                try:
                    decoded = decode_record(seq, grammar, glyph_decoder)
                    stray_total += len(decoded["stray_glyphs"])
                    heuristic_overlong += int(decoded["heuristic_over_41_chars"])
                    rows.append({
                        "arc_relative_path": rel,
                        "arc_sha256": arc_sha,
                        "resource_name": e["name"],
                        "record_index": ri,
                        "text": decoded["text"],
                        "stray_glyph_count": len(decoded["stray_glyphs"]),
                        "stray_glyphs": decoded["stray_glyphs"],
                        "visual_line_count": decoded["visual_line_count"],
                        "line_lengths_chars": decoded["line_lengths_chars"],
                        "heuristic_over_41_chars": decoded["heuristic_over_41_chars"],
                        "speech_count_from_delimiters": decoded["speech_count_from_delimiters"],
                        "control_count": len(decoded["controls"]),
                        "parse_status": "OK",
                    })
                except Exception as exc:
                    rows.append({
                        "arc_relative_path": rel,
                        "arc_sha256": arc_sha,
                        "resource_name": e["name"],
                        "record_index": ri,
                        "text": None,
                        "stray_glyph_count": None,
                        "stray_glyphs": None,
                        "visual_line_count": None,
                        "line_lengths_chars": None,
                        "heuristic_over_41_chars": None,
                        "speech_count_from_delimiters": None,
                        "control_count": None,
                        "parse_status": f"ERROR: {exc!r}",
                    })
                    findings.append({
                        "category": "MESSAGE_RECORD_PARSE",
                        "owner_path": f"{owner}::record={ri}",
                        "reason": repr(exc),
                        "release_severity": "BLOCKED",
                    })

            if stray_total:
                findings.append({
                    "category": "MESSAGE_STRAY_GLYPH",
                    "owner_path": owner,
                    "count": stray_total,
                    "release_severity": "NEEDS_REVIEW",
                })
            if heuristic_overlong:
                findings.append({
                    "category": "MESSAGE_HEURISTIC_OVERLONG",
                    "owner_path": owner,
                    "count": heuristic_overlong,
                    "release_severity": "NEEDS_LAYOUT_MEASUREMENT",
                    "note": "41-character threshold is historical scanner evidence only; actual TNF/widget width validation is required.",
                })

            resource["parse_status"] = "OK"
        except Exception as exc:
            resource["parse_status"] = f"ERROR: {exc!r}"
            findings.append({
                "category": "MESSAGE_RESOURCE_PARSE",
                "owner_path": owner,
                "reason": repr(exc),
                "release_severity": "BLOCKED",
            })

        resources.append(resource)

    return resources, rows, findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Utage GSM/FIM census")
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    root = args.root.resolve()
    out = args.out.resolve()
    if not root.is_dir():
        print(f"missing root: {root}", file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)

    try:
        require_hash(SAFE_ARC_PATH, EXPECTED_SAFE_ARC_SHA256)
        require_hash(FIM_CONTRACT_PATH, EXPECTED_FIM_CONTRACT_SHA256)
        require_hash(TEXT_SCANNER_PATH, EXPECTED_TEXT_SCANNER_SHA256)
        safe_arc = load_module("basara_safe_arc", SAFE_ARC_PATH)
        grammar = load_module("basara_fim_contract", FIM_CONTRACT_PATH)
        glyph_decoder = load_module("basara_text_scanner", TEXT_SCANNER_PATH)
    except Exception as exc:
        print(f"dependency failure: {exc}", file=sys.stderr)
        return 2

    resources = []
    rows = []
    findings = []
    arc_errors = []

    for p in sorted(root.rglob("*.arc")):
        try:
            rr, tx, ff = scan_arc(p, root, safe_arc, grammar, glyph_decoder)
            resources.extend(rr)
            rows.extend(tx)
            findings.extend(ff)
        except Exception as exc:
            arc_errors.append({
                "arc": p.relative_to(root).as_posix(),
                "error": repr(exc),
            })

    summary = {
        "schema": SCHEMA,
        "arc_errors": len(arc_errors),
        "message_resources": len(resources),
        "message_records": len(rows),
        "record_parse_errors": sum(r["parse_status"] != "OK" for r in rows),
        "fim_contract_fail_resources": sum(r["fim_contract_status"] == "FAIL" for r in resources),
        "resources_without_fim_pair": sum(r["fim_contract_status"] == "NO_FIM_PAIR" for r in resources),
        "stray_glyph_records": sum((r["stray_glyph_count"] or 0) > 0 for r in rows),
        "heuristic_overlong_records": sum(r["heuristic_over_41_chars"] is True for r in rows),
        "finding_count": len(findings),
        "release_pass": False,
        "release_pass_reason": "Width/layout semantics and user-visible classification remain separate release gates even when grammar/FIM contract is clean.",
    }

    (out / "MESSAGE_CENSUS.json").write_text(json.dumps({
        "summary": summary,
        "resources": resources,
        "records": rows,
        "findings": findings,
        "arc_errors": arc_errors,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fields = [
        "arc_relative_path", "arc_sha256", "resource_name", "record_index", "text",
        "stray_glyph_count", "visual_line_count", "line_lengths_chars",
        "heuristic_over_41_chars", "speech_count_from_delimiters", "control_count",
        "parse_status",
    ]
    with (out / "MESSAGE_CENSUS.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(json.dumps(summary, indent=2))
    if arc_errors or summary["record_parse_errors"] or summary["fim_contract_fail_resources"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
