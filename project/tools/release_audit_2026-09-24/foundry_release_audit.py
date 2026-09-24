#!/usr/bin/env python3
"""
BASARA Foundry release audit orchestrator — bootstrap v0.1
2026-09-24

READ-ONLY. This tool never mutates the game tree.

Current implemented stages:
  - bind run metadata/tool hashes
  - hash/classify every file under LIVE_ROOT
  - parse every ARC using the pinned canonical safe_arc.py
  - emit complete ARC member inventory
  - invoke the existing Resource Ownership Analyzer
  - aggregate parse/tool gaps into UNRESOLVED.json
  - emit SHA256SUMS.json and AUDIT_SUMMARY.md

Intentionally NOT claimed complete yet:
  - texture semantic census
  - GSM/FIM message census
  - PAM/media census
  - loose UI/metadata semantic census
  - donor matcher sweep
  - runtime acceptance merge

Until those are wired, successful execution exits 1 (engineering incomplete),
never 0.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "BASARA_FOUNDRY_RELEASE_AUDIT_V0_3"
EXPECTED_SAFE_ARC_SHA256 = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"
EXPECTED_XET_DECODER_SHA256 = "ec8746755dc1c60fc03c19811a96a90faa70821a3970d781f167f00376051b0c"
R_TEXTURE = 0x241F5DEB

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
OWNERSHIP_TOOL_PATH = TOOLS_DIR / "resource_ownership_2026-09-23" / "basara_resource_ownership.py"
XET_DECODER_PATH = TOOLS_DIR.parent / "texture_tools" / "xet_recovery_2026-09-23" / "foundry_xet_decoder_20260923.py"
MESSAGE_CENSUS_TOOL_PATH = HERE / "message_census.py"
DONOR_MATCHER_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "utage_donor_matcher_v5.py"
MEDIA_CENSUS_TOOL_PATH = HERE / "media_census.py"
PLATFORM_CENSUS_TOOL_PATH = HERE / "platform_census.py"
TERMINOLOGY_JSON_PATH = TOOLS_DIR.parent / "terminology" / "canonical_english_terminology_2026-09-24.json"
TERMINOLOGY_VALIDATOR_PATH = TOOLS_DIR.parent / "terminology" / "validate_terminology.py"
RUNTIME_MATRIX_TEMPLATE_PATH = TOOLS_DIR.parent / "runtime" / "runtime_acceptance_matrix_2026-09-24.json"
RUNTIME_MATRIX_VALIDATOR_PATH = TOOLS_DIR.parent / "runtime" / "validate_runtime_matrix.py"
FONT_CENSUS_TOOL_PATH = HERE / "font_contract_census.py"
LAYOUT_CENSUS_TOOL_PATH = HERE / "layout_census.py"
ORCHESTRATION_CLI_PATH = TOOLS_DIR.parent / "orchestration" / "foundry.py"

MANDATORY_PLACEHOLDER_OUTPUTS = (
    "TEXTURE_CENSUS.json",
    "MESSAGE_CENSUS.json",
    "MEDIA_CENSUS.json",
    "LOOSE_UI_AND_METADATA_CENSUS.json",
    "DONOR_CANDIDATES.json",
)

FILE_CLASS_RULES = (
    ("ARC", {".arc"}),
    ("EXECUTABLE", {".bin", ".elf", ".self", ".sprx"}),
    ("FONT", {".tnf", ".otf", ".ttf"}),
    ("XET_TEX_LOOSE", {".xet", ".tex"}),
    ("MOVIE_PAM", {".pam", ".pamf"}),
    ("CONFIG_METADATA", {".sfo", ".xml", ".ini", ".cfg", ".json"}),
    ("IMAGE", {".png", ".jpg", ".jpeg", ".dds", ".bmp", ".tga"}),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def classify_file(path: Path) -> str:
    name = path.name.upper()
    suffix = path.suffix.lower()
    parts_upper = {p.upper() for p in path.parts}
    if "TROPDIR" in parts_upper or name.startswith("TROP"):
        return "TROPHY"
    for cls, suffixes in FILE_CLASS_RULES:
        if suffix in suffixes:
            return cls
    return "OTHER"


def stable_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def load_module_from_path(name: str, path: Path):
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


def dependency_record(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "sha256": None,
            "expected_sha256": expected_sha256,
            "hash_ok": False if expected_sha256 else None,
            "hash_match_form": None,
        }

    data = path.read_bytes()
    actual = sha256_bytes(data)
    candidates = {"raw": actual}

    # Historical Foundry source hashes were sometimes recorded from Windows
    # CRLF working copies, while GitHub Actions checks out LF. For UTF-8 text
    # dependencies, accept only byte streams that differ solely by newline
    # normalization. Any other content drift still fails closed.
    try:
        text = data.decode("utf-8")
        lf = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        crlf = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8")
        candidates["utf8_lf"] = sha256_bytes(lf)
        candidates["utf8_crlf"] = sha256_bytes(crlf)
    except UnicodeDecodeError:
        pass

    match_form = None
    if expected_sha256:
        for form, digest in candidates.items():
            if digest == expected_sha256:
                match_form = form
                break

    return {
        "path": str(path),
        "exists": True,
        "sha256": actual,
        "expected_sha256": expected_sha256,
        "hash_ok": match_form is not None if expected_sha256 else None,
        "hash_match_form": match_form,
        "equivalent_text_hashes": candidates if expected_sha256 else None,
    }


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def tree_digest(files: list[dict[str, Any]]) -> str | None:
    if any(r.get("status") != "OK" or not r.get("sha256") for r in files):
        return None
    h = hashlib.sha256()
    for r in sorted(files, key=lambda x: x["relative_path"]):
        line = f"{r['relative_path']}\0{r['size']}\0{r['sha256']}\n".encode("utf-8")
        h.update(line)
    return h.hexdigest()


def resolve_snapshot_db(path: Path) -> Path:
    p = path.resolve()
    if p.is_file() and p.name == "index.sqlite3":
        return p
    if p.is_dir() and (p / "index.sqlite3").is_file():
        return p / "index.sqlite3"
    if p.is_dir() and (p / ".foundry" / "CURRENT_SNAPSHOT").is_file():
        sid = (p / ".foundry" / "CURRENT_SNAPSHOT").read_text(encoding="ascii").strip()
        return p / ".foundry" / "snapshots" / sid / "index.sqlite3"
    if p.is_dir() and (p / "CURRENT_SNAPSHOT").is_file():
        sid = (p / "CURRENT_SNAPSHOT").read_text(encoding="ascii").strip()
        return p / "snapshots" / sid / "index.sqlite3"
    raise ValueError(f"cannot resolve Foundry snapshot database from {p}")


def verify_snapshot_binding(snapshot_db: Path, live_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    proc = subprocess.run(
        [sys.executable, str(ORCHESTRATION_CLI_PATH), "verify", str(snapshot_db), "--root", str(live_root)],
        capture_output=True, text=True
    )
    try:
        report = json.loads(proc.stdout)
    except Exception as exc:
        return None, f"snapshot verifier did not return JSON: {exc!r}; stderr={proc.stderr[-2000:]}"
    if proc.returncode != 0 or not report.get("match"):
        return report, "current live tree no longer matches supplied snapshot"
    return report, None


def snapshot_file_rows(snapshot_db: Path, root: Path) -> tuple[list[dict[str, Any]], str]:
    conn = sqlite3.connect(snapshot_db)
    conn.row_factory = sqlite3.Row
    meta_row = conn.execute("SELECT value FROM metadata WHERE key='snapshot_id'").fetchone()
    snapshot_id = json.loads(meta_row["value"]) if meta_row else ""
    rows = []
    for r in conn.execute("SELECT path,size,sha256 FROM files ORDER BY path"):
        p = root / r["path"]
        rows.append({
            "relative_path": r["path"],
            "size": r["size"],
            "sha256": r["sha256"],
            "class": classify_file(p),
            "status": "OK",
            "error": None,
        })
    conn.close()
    return rows, snapshot_id


def snapshot_arc_member_rows(snapshot_db: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conn = sqlite3.connect(snapshot_db)
    conn.row_factory = sqlite3.Row
    rows = []
    unresolved = []
    for r in conn.execute("""
        SELECT f.path arc_relative_path,f.sha256 arc_sha256,r.member_index,r.internal_path,
               r.type_hex,r.flags,r.compressed_size,r.stored_sha256,
               r.declared_raw_size,r.actual_raw_size,r.raw_sha256,r.codec,r.warning
        FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id
        ORDER BY f.path,r.member_index
    """):
        d = dict(r)
        rows.append({
            "arc_relative_path": d["arc_relative_path"],
            "arc_sha256": d["arc_sha256"],
            "member_index": d["member_index"],
            "internal_path": d["internal_path"],
            "type_hash": d["type_hex"],
            "flags": d["flags"],
            "stored_size": d["compressed_size"],
            "stored_sha256": d["stored_sha256"],
            "expanded_declared_size": d["declared_raw_size"],
            "expanded_actual_size": d["actual_raw_size"],
            "expanded_sha256": d["raw_sha256"],
            "codec": d["codec"],
            "warning": d["warning"],
        })
        if d["warning"]:
            unresolved.append({
                "category": "ARC_WARNING",
                "owner_path": f"{d['arc_relative_path']}::{d['member_index']}::{d['internal_path']}",
                "reason": d["warning"],
                "required_next_evidence": "Retain warning; production writes must preserve current decoded-size contract.",
                "recommended_tool": "safe_arc.py",
                "release_severity": "NEEDS_REVIEW",
            })
    for r in conn.execute("SELECT f.path,a.error FROM arcs a JOIN files f ON f.id=a.file_id WHERE a.parse_status!='OK' ORDER BY f.path"):
        unresolved.append({
            "category": "ARC_PARSE",
            "owner_path": r["path"],
            "reason": r["error"],
            "required_next_evidence": "Inspect exact current ARC structure; do not repair during audit.",
            "recommended_tool": "safe_arc.py / current ARC forensic workflow",
            "release_severity": "BLOCKED",
        })
    conn.close()
    return rows, unresolved


def run_snapshot_ownership(snapshot_db: Path, outdir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    target = outdir / "_ownership_stage"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(ORCHESTRATION_CLI_PATH), "export-ownership", str(snapshot_db), "--out", str(target)],
        capture_output=True, text=True
    )
    report_path = target / "resource_ownership.json"
    if proc.returncode != 0 or not report_path.is_file():
        unresolved.append({
            "category": "OWNERSHIP_SNAPSHOT_EXPORT",
            "owner_path": str(snapshot_db),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Repair snapshot ownership export; never fall back silently to filesystem-order inference.",
            "recommended_tool": "project/orchestration/foundry.py export-ownership",
            "release_severity": "BLOCKED",
        })
        return None, unresolved
    report = json.loads(report_path.read_text(encoding="utf-8"))
    atomic_write_json(outdir / "RESOURCE_OWNERSHIP.json", report)
    divergent = [g for g in report.get("exact_duplicate_classes", []) if g.get("classification") in {"DIVERGENT", "UNRESOLVED_COMPRESSION"}]
    atomic_write_json(outdir / "DIVERGENT_PROVIDERS.json", divergent)
    for g in divergent:
        unresolved.append({
            "category": "DIVERGENT_PROVIDER",
            "owner_path": g.get("exact_path"),
            "reason": g.get("risk") or g.get("classification"),
            "required_next_evidence": "Disposition intentional variant vs equivalence sync; runtime/load-family evidence required for precedence claims.",
            "recommended_tool": "Foundry snapshot ownership + RPCS3 evidence",
            "release_severity": "NEEDS_REVIEW",
        })
    return report, unresolved


def scan_files(root: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        try:
            st = p.stat()
            rows.append({
                "relative_path": stable_rel(p, root),
                "size": st.st_size,
                "sha256": sha256_file(p),
                "class": classify_file(p),
                "status": "OK",
                "error": None,
            })
        except Exception as exc:
            rows.append({
                "relative_path": stable_rel(p, root),
                "size": None,
                "sha256": None,
                "class": classify_file(p),
                "status": "ERROR",
                "error": repr(exc),
            })
    return rows


def arc_member_rows(root: Path, safe_arc) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for arc_path in sorted(root.rglob("*.arc")):
        rel = stable_rel(arc_path, root)
        try:
            data = arc_path.read_bytes()
            arc_sha = sha256_bytes(data)
            entries = safe_arc.parse_arc(data)
        except Exception as exc:
            unresolved.append({
                "category": "ARC_PARSE",
                "owner_path": rel,
                "reason": repr(exc),
                "required_next_evidence": "Inspect exact current ARC structure; do not repair during audit.",
                "recommended_tool": "safe_arc.py / current ARC forensic workflow",
                "release_severity": "BLOCKED",
            })
            continue

        for e in entries:
            raw = e["raw"]
            stored = e["stored"]
            rows.append({
                "arc_relative_path": rel,
                "arc_sha256": arc_sha,
                "member_index": e["index"],
                "internal_path": e["name"],
                "type_hash": f"0x{e['type_hash']:08X}",
                "flags": e["flags"],
                "stored_size": e["compressed_size"],
                "stored_sha256": sha256_bytes(stored),
                "expanded_declared_size": e["raw_size"],
                "expanded_actual_size": len(raw),
                "expanded_sha256": sha256_bytes(raw),
                "codec": e["codec"],
                "warning": e["warning"],
            })
            if e["warning"]:
                unresolved.append({
                    "category": "ARC_WARNING",
                    "owner_path": f"{rel}::{e['index']}::{e['name']}",
                    "reason": e["warning"],
                    "required_next_evidence": "Retain warning; production writes must preserve current decoded-size contract.",
                    "recommended_tool": "safe_arc.py",
                    "release_severity": "NEEDS_REVIEW",
                })
    return rows, unresolved



def texture_census(root: Path, safe_arc, xet_decoder) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    review_count = 0

    for arc_path in sorted(root.rglob("*.arc")):
        rel = stable_rel(arc_path, root)
        try:
            data = arc_path.read_bytes()
            arc_sha = sha256_bytes(data)
            entries = safe_arc.parse_arc(data)
        except Exception:
            # ARC-level parse failure is already emitted by arc_member_rows.
            continue

        for e in entries:
            if e["type_hash"] != R_TEXTURE:
                continue
            raw = e["raw"]
            base = {
                "arc_relative_path": rel,
                "arc_sha256": arc_sha,
                "member_index": e["index"],
                "internal_path": e["name"],
                "raw_sha256": sha256_bytes(raw),
                "width": None,
                "height": None,
                "mip_count": None,
                "format_id": None,
                "version_flags": None,
                "tex_flags": None,
                "flags": None,
                "mip_offsets": None,
                "decoded_rgba_sha256": None,
                "decoder_status": None,
                "semantic_classification": "UNKNOWN_REVIEW",
            }
            try:
                info = xet_decoder.xet_info(raw)
                base.update({
                    "width": info.width,
                    "height": info.height,
                    "mip_count": info.mip_count,
                    "format_id": f"0x{info.format_id:02X}",
                    "version_flags": f"0x{info.version_flags:08X}",
                    "tex_flags": f"0x{info.tex_flags:08X}",
                    "flags": f"0x{info.flags:08X}",
                    "mip_offsets": list(info.mip_offsets),
                })

                validated = xet_decoder.validate(raw)
                rgba = xet_decoder.decode_rgba(raw, 0)
                base["decoded_rgba_sha256"] = sha256_bytes(rgba)
                base["decoder_status"] = "DECODED_LEVEL0"
                base["validated_levels"] = validated.get("levels")
                if info.format_id == 0x15:
                    base["read_contract"] = "DXT3_BC2_FIXTURE_VERIFIED_READ_ONLY"
            except Exception as exc:
                base["decoder_status"] = "UNSUPPORTED_OR_PARSE_ERROR"
                unresolved.append({
                    "category": "TEXTURE_PARSE",
                    "owner_path": f"{rel}::{e['index']}::{e['name']}",
                    "reason": repr(exc),
                    "required_next_evidence": "Classify format/layout with current XET forensic workflow; do not guess.",
                    "recommended_tool": "foundry_xet_decoder_20260923.py / texture research gate",
                    "release_severity": "BLOCKED",
                })

            rows.append(base)
            review_count += 1

    if review_count:
        unresolved.append({
            "category": "TEXTURE_SEMANTIC_REVIEW_PENDING",
            "owner_path": "TEXTURE_CENSUS.json",
            "reason": f"{review_count} rTexture providers inventoried; semantic English/Japanese/mixed classification is not automated and remains UNKNOWN_REVIEW until visual/context review.",
            "required_next_evidence": "Generate review previews/contact sheets and disposition every user-visible texture identity using ownership + SH/context evidence.",
            "recommended_tool": "release auditor + Donor Matcher V5.1 + visual review",
            "release_severity": "NEEDS_REVIEW",
        })
    return rows, unresolved


def run_ownership(root: Path, outdir: Path, logs: list[Path]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    target = outdir / "_ownership_stage"
    target.mkdir(parents=True, exist_ok=True)

    # Analyzer currently accepts one RPCS3 log. If several are supplied, run the
    # first now and explicitly record that multi-log merge remains future work.
    cmd = [sys.executable, str(OWNERSHIP_TOOL_PATH), str(root), "--out", str(target)]
    if logs:
        cmd += ["--rpcs3-log", str(logs[0])]
        if len(logs) > 1:
            unresolved.append({
                "category": "OWNERSHIP_LOG_MERGE",
                "owner_path": None,
                "reason": f"{len(logs)} RPCS3 logs supplied; bootstrap analyzer consumes one per run.",
                "required_next_evidence": "Implement deterministic multi-log order merge in orchestrator.",
                "recommended_tool": "basara_resource_ownership.py",
                "release_severity": "NEEDS_REVIEW",
            })

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        unresolved.append({
            "category": "OWNERSHIP_TOOL",
            "owner_path": str(OWNERSHIP_TOOL_PATH),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Fix tool/dependency failure; do not infer ownership manually from filesystem order.",
            "recommended_tool": "basara_resource_ownership.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    report_path = target / "resource_ownership.json"
    if not report_path.is_file():
        unresolved.append({
            "category": "OWNERSHIP_TOOL",
            "owner_path": str(report_path),
            "reason": "analyzer returned success but expected JSON was not produced",
            "required_next_evidence": "Investigate analyzer output contract.",
            "recommended_tool": "basara_resource_ownership.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    report = json.loads(report_path.read_text(encoding="utf-8"))
    atomic_write_json(outdir / "RESOURCE_OWNERSHIP.json", report)

    divergent = [
        g for g in report.get("exact_duplicate_classes", [])
        if g.get("classification") in {"DIVERGENT", "UNRESOLVED_COMPRESSION"}
    ]
    atomic_write_json(outdir / "DIVERGENT_PROVIDERS.json", divergent)
    for g in divergent:
        unresolved.append({
            "category": "DIVERGENT_PROVIDER",
            "owner_path": g.get("exact_path"),
            "reason": g.get("risk") or g.get("classification"),
            "required_next_evidence": "Disposition intentional variant vs equivalence sync; runtime/load-family evidence required for precedence claims.",
            "recommended_tool": "basara_resource_ownership.py + RPCS3 evidence",
            "release_severity": "NEEDS_REVIEW",
        })

    return report, unresolved



def run_message_census(root: Path, outdir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    stage = outdir / "_message_stage"
    stage.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(MESSAGE_CENSUS_TOOL_PATH), str(root), "--out", str(stage)],
        capture_output=True, text=True
    )
    if proc.returncode not in (0, 1):
        print(f"MESSAGE_CENSUS_TOOL failure: exit={proc.returncode}; stderr={proc.stderr[-4000:]}", file=sys.stderr)
        unresolved.append({
            "category": "MESSAGE_CENSUS_TOOL",
            "owner_path": str(MESSAGE_CENSUS_TOOL_PATH),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Fix census dependency/infrastructure failure; do not fall back to naive Unicode grep.",
            "recommended_tool": "message_census.py + recovered GSM/FIM toolchain",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    jp = stage / "MESSAGE_CENSUS.json"
    cp = stage / "MESSAGE_CENSUS.csv"
    if not jp.is_file() or not cp.is_file():
        unresolved.append({
            "category": "MESSAGE_CENSUS_TOOL",
            "owner_path": str(stage),
            "reason": "message census completed without mandatory outputs",
            "required_next_evidence": "Restore stable output contract.",
            "recommended_tool": "message_census.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    atomic_write_text(outdir / "MESSAGE_CENSUS.json", jp.read_text(encoding="utf-8"))
    atomic_write_text(outdir / "MESSAGE_CENSUS.csv", cp.read_text(encoding="utf-8"))
    report = json.loads(jp.read_text(encoding="utf-8"))

    for item in report.get("findings", []):
        unresolved.append({
            "category": item.get("category", "MESSAGE_FINDING"),
            "owner_path": item.get("owner_path"),
            "reason": item.get("reason") or f"count={item.get('count')}",
            "required_next_evidence": item.get("note") or "Review with current GSM/FIM + layout/terminology evidence.",
            "recommended_tool": "message_census.py / current message production workflow",
            "release_severity": item.get("release_severity", "NEEDS_REVIEW"),
        })
    for err in report.get("arc_errors", []):
        unresolved.append({
            "category": "MESSAGE_ARC_PARSE",
            "owner_path": err.get("arc"),
            "reason": err.get("error"),
            "required_next_evidence": "Resolve exact ARC/parser blocker; no silent skip.",
            "recommended_tool": "safe_arc.py + message census",
            "release_severity": "BLOCKED",
        })

    unresolved.append({
        "category": "MESSAGE_WIDTH_LAYOUT_VALIDATION_PENDING",
        "owner_path": "MESSAGE_CENSUS.json",
        "reason": "Grammar/FIM census does not yet prove pixel-width fit against active TNF/CSA/widget geometry.",
        "required_next_evidence": "Integrate a reusable TNF/CSA + widget width validator; disposition every over-budget/at-risk row.",
        "recommended_tool": "future layout-width validator",
        "release_severity": "NEEDS_REVIEW",
    })
    return report, unresolved



def run_inventory_only(root: Path, stage: Path) -> tuple[Path | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    stage.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(OWNERSHIP_TOOL_PATH), str(root), "--out", str(stage)],
        capture_output=True, text=True
    )
    resources_csv = stage / "resources.csv"
    if proc.returncode != 0 or not resources_csv.is_file():
        unresolved.append({
            "category": "REFERENCE_INVENTORY",
            "owner_path": str(root),
            "reason": f"ownership inventory failed exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Restore reference-root inventory before donor matching.",
            "recommended_tool": "basara_resource_ownership.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved
    return resources_csv, unresolved


def run_donor_matcher(live_root: Path, sh_root: Path | None, outdir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    if sh_root is None or not sh_root.is_dir():
        unresolved.append({
            "category": "DONOR_REFERENCE_ROOT",
            "owner_path": str(sh_root) if sh_root else None,
            "reason": "Samurai Heroes root not supplied or not readable.",
            "required_next_evidence": "Run audit with --sh-root pointing to the exact official English Samurai Heroes tree.",
            "recommended_tool": "Utage Donor Matcher V5.1",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    utage_inventory = outdir / "_ownership_stage" / "resources.csv"
    if not utage_inventory.is_file():
        unresolved.append({
            "category": "DONOR_TARGET_INVENTORY",
            "owner_path": str(utage_inventory),
            "reason": "Current-live ownership resources.csv is missing.",
            "required_next_evidence": "Complete ownership analyzer stage first.",
            "recommended_tool": "basara_resource_ownership.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    sh_inventory, inv_unresolved = run_inventory_only(sh_root, outdir / "_sh_ownership_stage")
    unresolved.extend(inv_unresolved)
    if sh_inventory is None:
        return None, unresolved

    report = outdir / "DONOR_CANDIDATES.json"
    harness = outdir / "DONOR_HARNESS_PLAN.json"
    graft = outdir / "DONOR_GRAFT_CANDIDATES.json"
    cmd = [
        sys.executable, str(DONOR_MATCHER_PATH),
        "--utage", str(utage_inventory),
        "--sh-en", str(sh_inventory),
        "--report", str(report),
        "--harness-plan", str(harness),
        "--graft-plan", str(graft),
        "--utage-root", str(live_root),
        "--sh-root", str(sh_root),
        "--duplicate-policy", "REPORT_ONLY",
        "--input-format", "foundry",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not report.is_file():
        unresolved.append({
            "category": "DONOR_MATCHER_TOOL",
            "owner_path": str(DONOR_MATCHER_PATH),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Fix matcher/inventory compatibility; do not manually infer donor safety from similar filenames.",
            "recommended_tool": "Utage Donor Matcher V5.1",
            "release_severity": "BLOCKED",
        })
        return None, unresolved

    payload = json.loads(report.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    by_decision: dict[str, int] = {}
    by_provider_status: dict[str, int] = {}
    for rec in records:
        d = rec.get("decision") or "UNKNOWN"
        by_decision[d] = by_decision.get(d, 0) + 1
        p = rec.get("provider_status") or "NONE"
        by_provider_status[p] = by_provider_status.get(p, 0) + 1

    summary = {
        "target_records": len(records),
        "by_decision": by_decision,
        "by_provider_status": by_provider_status,
        "harness_plan_file": harness.name if harness.is_file() else None,
        "graft_plan_file": graft.name if graft.is_file() else None,
        "policy": "REPORT_ONLY; candidate discovery never auto-patches game files",
    }
    return summary, unresolved



def run_simple_census(tool: Path, root: Path, outdir: Path, stage_name: str,
                      json_name: str, csv_name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    stage = outdir / f"_{stage_name}_stage"
    stage.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(tool), str(root), "--out", str(stage)],
        capture_output=True, text=True
    )
    jp, cp = stage / json_name, stage / csv_name
    if proc.returncode not in (0, 1) or not jp.is_file() or not cp.is_file():
        unresolved.append({
            "category": f"{stage_name.upper()}_CENSUS_TOOL",
            "owner_path": str(tool),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Fix read-only census tool/output contract; no silent omission.",
            "recommended_tool": tool.name,
            "release_severity": "BLOCKED",
        })
        return None, unresolved
    atomic_write_text(outdir / json_name, jp.read_text(encoding="utf-8"))
    atomic_write_text(outdir / csv_name, cp.read_text(encoding="utf-8"))
    report = json.loads(jp.read_text(encoding="utf-8"))
    for err in report.get("errors", []):
        unresolved.append({
            "category": f"{stage_name.upper()}_CENSUS_ERROR",
            "owner_path": err.get("path"),
            "reason": err.get("error"),
            "required_next_evidence": "Resolve exact current-live read/parse failure.",
            "recommended_tool": tool.name,
            "release_severity": "BLOCKED",
        })
    for item in report.get("unresolved", []):
        unresolved.append({
            "category": item.get("category", f"{stage_name.upper()}_CENSUS_FINDING"),
            "owner_path": item.get("owner_path"),
            "reason": item.get("reason"),
            "required_next_evidence": item.get("required_next_evidence") or "Review with the current canonical domain workflow.",
            "recommended_tool": item.get("recommended_tool") or tool.name,
            "release_severity": item.get("release_severity", "NEEDS_REVIEW"),
        })
    return report, unresolved


def run_terminology_gate(outdir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    proc = subprocess.run(
        [sys.executable, str(TERMINOLOGY_VALIDATOR_PATH), str(TERMINOLOGY_JSON_PATH), "--release-gate"],
        capture_output=True, text=True
    )
    if proc.returncode not in (0, 1):
        unresolved.append({
            "category": "TERMINOLOGY_TOOL",
            "owner_path": str(TERMINOLOGY_JSON_PATH),
            "reason": f"exit={proc.returncode}; stderr={proc.stderr[-4000:]}",
            "required_next_evidence": "Repair machine-readable terminology ledger/validator before release QA.",
            "recommended_tool": "validate_terminology.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved
    try:
        report = json.loads(proc.stdout)
    except Exception as exc:
        unresolved.append({
            "category": "TERMINOLOGY_TOOL",
            "owner_path": str(TERMINOLOGY_VALIDATOR_PATH),
            "reason": f"invalid JSON output: {exc!r}",
            "required_next_evidence": "Restore stable validator output.",
            "recommended_tool": "validate_terminology.py",
            "release_severity": "BLOCKED",
        })
        return None, unresolved
    atomic_write_json(outdir / "TERMINOLOGY_STATUS.json", report)
    for b in report.get("release_blockers", []):
        unresolved.append({
            "category": "TERMINOLOGY_BLOCKER",
            "owner_path": b.get("id"),
            "reason": f"status={b.get('status')} variants={b.get('variants')}",
            "required_next_evidence": "Resolve from official SH/context/current source, then update canonical terminology JSON.",
            "recommended_tool": "canonical_english_terminology_2026-09-24.json",
            "release_severity": "BLOCKED",
        })
    return report, unresolved



def prepare_runtime_matrix(outdir: Path, root_hash: str | None,
                           eboot_candidates: list[dict[str, Any]],
                           candidate_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    try:
        matrix = json.loads(RUNTIME_MATRIX_TEMPLATE_PATH.read_text(encoding="utf-8"))
        matrix["candidate"]["id"] = candidate_id
        matrix["candidate"]["live_root_sha256"] = root_hash
        matrix["candidate"]["created_utc"] = datetime.now(timezone.utc).isoformat()
        if len(eboot_candidates) == 1:
            matrix["candidate"]["eboot_sha256"] = eboot_candidates[0]["sha256"]
        else:
            matrix["candidate"]["eboot_sha256"] = None
        out_path = outdir / "RUNTIME_ACCEPTANCE_MATRIX.json"
        atomic_write_json(out_path, matrix)
        proc = subprocess.run(
            [sys.executable, str(RUNTIME_MATRIX_VALIDATOR_PATH), str(out_path)],
            capture_output=True, text=True
        )
        try:
            status = json.loads(proc.stdout)
        except Exception as exc:
            status = {"errors":[f"validator JSON failure: {exc!r}"],"blockers":[],"release_ready":False}
        atomic_write_json(outdir / "RUNTIME_ACCEPTANCE_STATUS.json", status)
        if status.get("errors"):
            unresolved.append({
                "category":"RUNTIME_MATRIX_BINDING",
                "owner_path":"RUNTIME_ACCEPTANCE_MATRIX.json",
                "reason":"; ".join(status["errors"]),
                "required_next_evidence":"Bind matrix to one complete current tree/EBOOT and repair validation errors.",
                "recommended_tool":"validate_runtime_matrix.py",
                "release_severity":"BLOCKED",
            })
        blockers=status.get("blockers",[])
        if blockers:
            unresolved.append({
                "category":"RUNTIME_ACCEPTANCE_INCOMPLETE",
                "owner_path":"RUNTIME_ACCEPTANCE_MATRIX.json",
                "reason":f"{len(blockers)} final-candidate runtime rows are not PASS.",
                "required_next_evidence":"Run exact routes on this candidate, attach screenshot/video/log evidence, and set PASS only when validator requirements are met.",
                "recommended_tool":"runtime_acceptance_matrix_2026-09-24.json",
                "release_severity":"BLOCKED",
            })
        return status, unresolved
    except Exception as exc:
        unresolved.append({
            "category":"RUNTIME_MATRIX_TOOL",
            "owner_path":str(RUNTIME_MATRIX_TEMPLATE_PATH),
            "reason":repr(exc),
            "required_next_evidence":"Restore runtime matrix template/validator.",
            "recommended_tool":"runtime acceptance tooling",
            "release_severity":"BLOCKED",
        })
        return None, unresolved


def placeholder_output(outdir: Path, filename: str, reason: str) -> None:
    atomic_write_json(outdir / filename, {
        "schema": SCHEMA,
        "status": "NOT_IMPLEMENTED",
        "reason": reason,
        "release_pass": False,
    })


def output_hashes(outdir: Path) -> dict[str, str]:
    result = {}
    for p in sorted(x for x in outdir.iterdir() if x.is_file() and x.name != "SHA256SUMS.json"):
        result[p.name] = sha256_file(p)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only BASARA Foundry release audit bootstrap")
    ap.add_argument("live_root", type=Path)
    ap.add_argument("--sh-root", type=Path, default=None)
    ap.add_argument("--rpcs3-log", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="Optional Foundry v0.2 snapshot/index. When supplied, exact file/member/ownership truth is reused after live-tree verification.")
    ap.add_argument("--allow-tool-drift", action="store_true",
                    help="Engineering-only override; recorded in metadata and never a release PASS.")
    args = ap.parse_args()

    live_root = args.live_root.resolve()
    outdir = args.out.resolve()
    logs = [p.resolve() for p in args.rpcs3_log]

    if not live_root.is_dir():
        print(f"ERROR: live root is not a directory: {live_root}", file=sys.stderr)
        return 3
    if live_root == outdir or outdir.is_relative_to(live_root):
        print("ERROR: --out must be outside LIVE_ROOT so audit output cannot pollute the scanned tree.", file=sys.stderr)
        return 3

    outdir.mkdir(parents=True, exist_ok=True)

    dependencies = {
        "safe_arc": dependency_record(SAFE_ARC_PATH, EXPECTED_SAFE_ARC_SHA256),
        "ownership_analyzer": dependency_record(OWNERSHIP_TOOL_PATH),
        "xet_decoder": dependency_record(XET_DECODER_PATH, EXPECTED_XET_DECODER_SHA256),
        "message_census": dependency_record(MESSAGE_CENSUS_TOOL_PATH),
        "donor_matcher": dependency_record(DONOR_MATCHER_PATH),
        "media_census": dependency_record(MEDIA_CENSUS_TOOL_PATH),
        "platform_census": dependency_record(PLATFORM_CENSUS_TOOL_PATH),
        "terminology_json": dependency_record(TERMINOLOGY_JSON_PATH),
        "terminology_validator": dependency_record(TERMINOLOGY_VALIDATOR_PATH),
        "runtime_matrix_template": dependency_record(RUNTIME_MATRIX_TEMPLATE_PATH),
        "runtime_matrix_validator": dependency_record(RUNTIME_MATRIX_VALIDATOR_PATH),
        "font_contract_census": dependency_record(FONT_CENSUS_TOOL_PATH),
        "layout_census": dependency_record(LAYOUT_CENSUS_TOOL_PATH),
        "orchestrator": dependency_record(Path(__file__).resolve()),
    }

    safe_ok = dependencies["safe_arc"]["exists"] and dependencies["safe_arc"]["hash_ok"]
    xet_ok = dependencies["xet_decoder"]["exists"] and dependencies["xet_decoder"]["hash_ok"]
    if (not safe_ok or not xet_ok) and not args.allow_tool_drift:
        atomic_write_json(outdir / "00_RUN_METADATA.json", {
            "schema": SCHEMA,
            "status": "DEPENDENCY_FAILURE",
            "dependencies": dependencies,
        })
        print("ERROR: canonical safe_arc.py or recovered XET decoder missing/hash-drifted; refusing audit.", file=sys.stderr)
        print(json.dumps({
            "safe_arc": dependencies["safe_arc"],
            "xet_decoder": dependencies["xet_decoder"],
        }, indent=2), file=sys.stderr)
        return 2

    safe_arc = load_module_from_path("basara_foundry_safe_arc", SAFE_ARC_PATH)
    xet_decoder = load_module_from_path("basara_foundry_xet_decoder", XET_DECODER_PATH)

    started = datetime.now(timezone.utc)
    started_local = datetime.now().astimezone()
    t0 = time.time()

    snapshot_db = resolve_snapshot_db(args.snapshot) if args.snapshot else None
    if snapshot_db and (live_root / "PS3_GAME").is_dir():
        live_root = (live_root / "PS3_GAME").resolve()
    snapshot_id = None
    snapshot_verify = None
    if snapshot_db:
        snapshot_verify, snapshot_error = verify_snapshot_binding(snapshot_db, live_root)
        if snapshot_error:
            atomic_write_json(outdir / "00_RUN_METADATA.json", {
                "schema": SCHEMA,
                "status": "SNAPSHOT_BINDING_FAILURE",
                "release_pass": False,
                "snapshot_db": str(snapshot_db),
                "snapshot_verification": snapshot_verify,
                "reason": snapshot_error,
            })
            print(f"ERROR: {snapshot_error}", file=sys.stderr)
            return 2
        files, snapshot_id = snapshot_file_rows(snapshot_db, live_root)
    else:
        files = scan_files(live_root)
    file_error_rows = [r for r in files if r["status"] != "OK"]
    live_tree_sha256 = tree_digest(files)

    atomic_write_json(outdir / "FILE_TREE_HASHES.json", {
        "schema": SCHEMA,
        "live_root_hint": str(live_root),
        "live_tree_sha256": live_tree_sha256,
        "snapshot_id": snapshot_id,
        "snapshot_db": str(snapshot_db) if snapshot_db else None,
        "snapshot_verification": snapshot_verify,
        "files": files,
    })
    write_csv(outdir / "FILE_TREE_HASHES.csv", files,
              ["relative_path", "size", "sha256", "class", "status", "error"])

    members, unresolved = snapshot_arc_member_rows(snapshot_db) if snapshot_db else arc_member_rows(live_root, safe_arc)
    atomic_write_json(outdir / "ARC_MEMBERS.json", {
        "schema": SCHEMA,
        "members": members,
    })
    write_csv(outdir / "ARC_MEMBERS.csv", members, [
        "arc_relative_path", "arc_sha256", "member_index", "internal_path",
        "type_hash", "flags", "stored_size", "stored_sha256",
        "expanded_declared_size", "expanded_actual_size", "expanded_sha256",
        "codec", "warning",
    ])

    for r in file_error_rows:
        unresolved.append({
            "category": "FILE_READ",
            "owner_path": r["relative_path"],
            "reason": r["error"],
            "required_next_evidence": "Restore readable current-live source or classify intentionally inaccessible.",
            "recommended_tool": "filesystem/hash audit",
            "release_severity": "BLOCKED",
        })

    ownership_report, ownership_unresolved = (run_snapshot_ownership(snapshot_db, outdir) if snapshot_db else run_ownership(live_root, outdir, logs))
    unresolved.extend(ownership_unresolved)

    textures, texture_unresolved = texture_census(live_root, safe_arc, xet_decoder)
    unresolved.extend(texture_unresolved)
    atomic_write_json(outdir / "TEXTURE_CENSUS.json", {
        "schema": SCHEMA,
        "semantic_policy": "Do not infer English/Japanese from eng-vs-jpn path or hash equality. UNKNOWN_REVIEW requires visual/context disposition.",
        "xet_0x15_policy": "decode/preview as fixture-proven DXT3/BC2; production writing remains fail-closed until runtime-certified",
        "textures": textures,
    })
    write_csv(outdir / "TEXTURE_CENSUS.csv", textures, [
        "arc_relative_path", "arc_sha256", "member_index", "internal_path",
        "raw_sha256", "width", "height", "mip_count", "format_id",
        "version_flags", "tex_flags", "flags", "mip_offsets",
        "decoded_rgba_sha256", "decoder_status", "semantic_classification",
    ])

    message_report, message_unresolved = run_message_census(live_root, outdir)
    unresolved.extend(message_unresolved)

    sh_root = args.sh_root.resolve() if args.sh_root else None
    donor_summary, donor_unresolved = run_donor_matcher(live_root, sh_root, outdir)
    unresolved.extend(donor_unresolved)

    media_report, media_unresolved = run_simple_census(
        MEDIA_CENSUS_TOOL_PATH, live_root, outdir, "media",
        "MEDIA_CENSUS.json", "MEDIA_CENSUS.csv")
    unresolved.extend(media_unresolved)

    platform_report, platform_unresolved = run_simple_census(
        PLATFORM_CENSUS_TOOL_PATH, live_root, outdir, "platform",
        "LOOSE_UI_AND_METADATA_CENSUS.json", "LOOSE_UI_AND_METADATA_CENSUS.csv")
    unresolved.extend(platform_unresolved)

    terminology_report, terminology_unresolved = run_terminology_gate(outdir)
    unresolved.extend(terminology_unresolved)

    font_report, font_unresolved = run_simple_census(
        FONT_CENSUS_TOOL_PATH, live_root, outdir, "font_contract",
        "FONT_CONTRACT_CENSUS.json", "FONT_CONTRACT_CENSUS.csv")
    unresolved.extend(font_unresolved)

    layout_report, layout_unresolved = run_simple_census(
        LAYOUT_CENSUS_TOOL_PATH, live_root, outdir, "layout",
        "LAYOUT_CENSUS.json", "LAYOUT_NODES.csv")
    unresolved.extend(layout_unresolved)
    if font_report is not None:
        unresolved.append({
            "category": "WIDGET_CAPACITY_VALIDATION_PENDING",
            "owner_path": "FONT_CONTRACT_CENSUS.json",
            "reason": "Font advances are now measurable, but active PSL/LSP widget bounds, margins, scale and route ownership are not yet joined to each message surface.",
            "required_next_evidence": "Join exact active message/font contract to proven layout node geometry before declaring overflow/fit.",
            "recommended_tool": "font_contract_census.py + proven PSL reader/runtime ownership evidence",
            "release_severity": "NEEDS_REVIEW",
        })

    # Runtime matrix is prepared after EBOOT discovery below; its rows remain
    # NOT_TESTED until evidence is attached for this exact candidate.

    # Deliberate fail-closed placeholders. They make incompleteness explicit and
    # keep the output contract stable while the proven domain parsers are wired.
    placeholder_reasons = {
    }
    for filename, reason in placeholder_reasons.items():
        placeholder_output(outdir, filename, reason)
        unresolved.append({
            "category": "AUDIT_STAGE_NOT_IMPLEMENTED",
            "owner_path": filename,
            "reason": reason,
            "required_next_evidence": "Wire the existing canonical domain tool without reimplementing its parser.",
            "recommended_tool": "See 2026-09-24 Release Audit Orchestrator implementation contract.",
            "release_severity": "BLOCKED",
        })

    eboot_candidates = [
        r for r in files
        if Path(r["relative_path"]).name.upper() in {"EBOOT.BIN", "EBOOT.ELF"}
        and r["sha256"]
    ]
    candidate_id = "AUDIT_" + started_local.strftime("%Y%m%d_%H%M%S")
    runtime_status, runtime_unresolved = prepare_runtime_matrix(
        outdir, live_tree_sha256, eboot_candidates, candidate_id)
    unresolved.extend(runtime_unresolved)

    atomic_write_json(outdir / "UNRESOLVED.json", {
        "schema": SCHEMA,
        "count": len(unresolved),
        "items": unresolved,
    })

    metadata = {
        "schema": SCHEMA,
        "status": "ENGINEERING_INCOMPLETE",
        "release_pass": False,
        "started_utc": started.isoformat(),
        "started_local": started_local.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - t0, 3),
        "live_root_hint": str(live_root),
        "live_tree_sha256": live_tree_sha256,
        "samurai_heroes_root_hint": str(args.sh_root.resolve()) if args.sh_root else None,
        "rpcs3_logs": [
            {"path": str(p), "sha256": sha256_file(p) if p.is_file() else None}
            for p in logs
        ],
        "dependencies": dependencies,
        "tool_drift_override": bool(args.allow_tool_drift),
        "file_count": len(files),
        "arc_member_count": len(members),
        "texture_provider_count": len(textures),
        "message_resource_count": (message_report or {}).get("summary", {}).get("message_resources"),
        "message_record_count": (message_report or {}).get("summary", {}).get("message_records"),
        "donor_summary": donor_summary,
        "media_summary": (media_report or {}).get("summary"),
        "platform_summary": (platform_report or {}).get("summary"),
        "terminology_summary": terminology_report,
        "font_contract_summary": (font_report or {}).get("summary"),
        "layout_summary": (layout_report or {}).get("summary"),
        "runtime_acceptance_summary": runtime_status,
        "unresolved_count": len(unresolved),
        "eboot_candidates": eboot_candidates,
        "ownership_summary": ownership_report.get("summary") if ownership_report else None,
    }
    atomic_write_json(outdir / "00_RUN_METADATA.json", metadata)

    summary_lines = [
        "# BASARA Foundry Release Audit — v0.3",
        "",
        f"- Status: **{metadata['status']}**",
        f"- Release pass: **NO**",
        f"- Files hashed: **{len(files)}**",
        f"- ARC members inventoried through canonical safe_arc: **{len(members)}**",
        f"- rTexture providers inventoried: **{len(textures)}**",
        f"- Message resources inventoried: **{(message_report or {}).get('summary', {}).get('message_resources', 'FAILED')}**",
        f"- Message records inventoried: **{(message_report or {}).get('summary', {}).get('message_records', 'FAILED')}**",
        f"- Unresolved/blocking rows: **{len(unresolved)}**",
        "",
        "## Implemented",
        "",
        "- Current-live file hash census",
        "- ARC member inventory using pinned safe_arc.py",
        "- Existing Resource Ownership Analyzer orchestration",
        "- Recovered XET metadata/decode census for supported formats, including fixture-proven 0x15 DXT3/BC2 read support",
        "- Recovered GSM/FIM grammar census + exact FIM contract verification",
        "- Donor Matcher V5.1 report-only sweep using current Utage + official SH ownership inventories",
        "- PAM/media inventory with hashes/container headers and explicit subtitle/runtime review states",
        "- PARAM.SFO/XMB/trophy/system-font/loose-resource inventory with read-only SFO parsing",
        "- machine-readable terminology release gate",
        "- read-only TNF/CSA font-contract census with real ASCII advance classification",
        "- read-only PSL geometry census with fixture-proven destination/source rectangles",
        "- final-candidate runtime acceptance matrix bound to the audited tree hash",
        "- Divergent-provider extraction",
        "- Explicit unresolved queue",
        "- Dependency/tool hash binding",
        "",
        "## Still required before this auditor can ever exit 0",
        "",
        "- texture semantic visual classification + production certification for currently read-only write formats such as 0x15 BC2",
        "- pixel-width/layout validation on top of the GSM/FIM census",
        "- PAM identity-remux + translated hardsub runtime certification",
        "- semantic/visual disposition of XMB/trophy/loose-platform census rows",
        "- completion of every generated runtime-acceptance row with exact-build evidence",
        "",
        "This bootstrap deliberately returns exit code 1 after a successful run. "
        "Unknown/not-yet-integrated stages are release blockers, never implicit PASS.",
        "",
    ]
    atomic_write_text(outdir / "AUDIT_SUMMARY.md", "\n".join(summary_lines))

    atomic_write_json(outdir / "SHA256SUMS.json", output_hashes(outdir))

    print(json.dumps({
        "status": metadata["status"],
        "file_count": len(files),
        "arc_member_count": len(members),
        "texture_provider_count": len(textures),
        "message_resource_count": (message_report or {}).get("summary", {}).get("message_resources"),
        "message_record_count": (message_report or {}).get("summary", {}).get("message_records"),
        "donor_summary": donor_summary,
        "media_summary": (media_report or {}).get("summary"),
        "platform_summary": (platform_report or {}).get("summary"),
        "terminology_summary": terminology_report,
        "runtime_acceptance_summary": runtime_status,
        "live_tree_sha256": live_tree_sha256,
        "unresolved_count": len(unresolved),
        "out": str(outdir),
    }, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
