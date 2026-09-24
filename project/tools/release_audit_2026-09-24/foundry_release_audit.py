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
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "BASARA_FOUNDRY_RELEASE_AUDIT_V0_1"
EXPECTED_SAFE_ARC_SHA256 = "f25c53e4ad78e18d5785b8aee197725377130ed9f562a9caa1000a1964bde91d"
EXPECTED_XET_DECODER_SHA256 = "d0ffe59abd91fa18bd5ec76bdf8d73fbe7595597b4f7ab3339a5d5de7fc58255"
R_TEXTURE = 0x241F5DEB

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
OWNERSHIP_TOOL_PATH = TOOLS_DIR / "resource_ownership_2026-09-23" / "basara_resource_ownership.py"
XET_DECODER_PATH = TOOLS_DIR.parent / "texture_tools" / "xet_recovery_2026-09-23" / "foundry_xet_decoder_20260923.py"

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
    spec.loader.exec_module(mod)
    return mod


def dependency_record(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "sha256": None,
            "expected_sha256": expected_sha256,
            "hash_ok": False if expected_sha256 else None,
        }
    actual = sha256_file(path)
    return {
        "path": str(path),
        "exists": True,
        "sha256": actual,
        "expected_sha256": expected_sha256,
        "hash_ok": actual == expected_sha256 if expected_sha256 else None,
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

                if info.format_id == 0x15:
                    base["decoder_status"] = "FORMAT_QUARANTINED_0X15"
                    unresolved.append({
                        "category": "XET_0X15_FORMAT_QUARANTINE",
                        "owner_path": f"{rel}::{e['index']}::{e['name']}",
                        "reason": "0x15 metadata parsed, but image decode intentionally withheld because BC2/DXT3 fixture evidence conflicts with the recovered decoder's BC3 mapping.",
                        "required_next_evidence": "Revalidate exact 0x15 Utage fixture and distinguish BC2-vs-BC3 alpha coding.",
                        "recommended_tool": "current XET recovery path + XET_0x15_DXT3_UTAGE_FIXTURE_2026-09-22",
                        "release_severity": "BLOCKED",
                    })
                else:
                    validated = xet_decoder.validate(raw)
                    rgba = xet_decoder.decode_rgba(raw, 0)
                    base["decoded_rgba_sha256"] = sha256_bytes(rgba)
                    base["decoder_status"] = "DECODED_LEVEL0"
                    base["validated_levels"] = validated.get("levels")
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
        return 2

    safe_arc = load_module_from_path("basara_foundry_safe_arc", SAFE_ARC_PATH)
    xet_decoder = load_module_from_path("basara_foundry_xet_decoder", XET_DECODER_PATH)

    started = datetime.now(timezone.utc)
    started_local = datetime.now().astimezone()
    t0 = time.time()

    files = scan_files(live_root)
    file_error_rows = [r for r in files if r["status"] != "OK"]

    atomic_write_json(outdir / "FILE_TREE_HASHES.json", {
        "schema": SCHEMA,
        "live_root_hint": str(live_root),
        "files": files,
    })
    write_csv(outdir / "FILE_TREE_HASHES.csv", files,
              ["relative_path", "size", "sha256", "class", "status", "error"])

    members, unresolved = arc_member_rows(live_root, safe_arc)
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

    ownership_report, ownership_unresolved = run_ownership(live_root, outdir, logs)
    unresolved.extend(ownership_unresolved)

    textures, texture_unresolved = texture_census(live_root, safe_arc, xet_decoder)
    unresolved.extend(texture_unresolved)
    atomic_write_json(outdir / "TEXTURE_CENSUS.json", {
        "schema": SCHEMA,
        "semantic_policy": "Do not infer English/Japanese from eng-vs-jpn path or hash equality. UNKNOWN_REVIEW requires visual/context disposition.",
        "xet_0x15_policy": "metadata-only quarantine; no image decode until fixture conflict is resolved",
        "textures": textures,
    })
    write_csv(outdir / "TEXTURE_CENSUS.csv", textures, [
        "arc_relative_path", "arc_sha256", "member_index", "internal_path",
        "raw_sha256", "width", "height", "mip_count", "format_id",
        "version_flags", "tex_flags", "flags", "mip_offsets",
        "decoded_rgba_sha256", "decoder_status", "semantic_classification",
    ])

    # Deliberate fail-closed placeholders. They make incompleteness explicit and
    # keep the output contract stable while the proven domain parsers are wired.
    placeholder_reasons = {
        "MESSAGE_CENSUS.json": "Recovered GSM/FIM production grammar not yet integrated into orchestrator.",
        "MEDIA_CENSUS.json": "PAM/media inventory/probe layer not yet integrated.",
        "LOOSE_UI_AND_METADATA_CENSUS.json": "PARAM.SFO/TROPDIR/XMB/loose semantic audit not yet integrated.",
        "DONOR_CANDIDATES.json": "Donor Matcher V5.1 orchestration not yet integrated.",
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

    atomic_write_json(outdir / "UNRESOLVED.json", {
        "schema": SCHEMA,
        "count": len(unresolved),
        "items": unresolved,
    })

    eboot_candidates = [
        r for r in files
        if Path(r["relative_path"]).name.upper() in {"EBOOT.BIN", "EBOOT.ELF"}
        and r["sha256"]
    ]

    metadata = {
        "schema": SCHEMA,
        "status": "ENGINEERING_INCOMPLETE",
        "release_pass": False,
        "started_utc": started.isoformat(),
        "started_local": started_local.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - t0, 3),
        "live_root_hint": str(live_root),
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
        "unresolved_count": len(unresolved),
        "eboot_candidates": eboot_candidates,
        "ownership_summary": ownership_report.get("summary") if ownership_report else None,
    }
    atomic_write_json(outdir / "00_RUN_METADATA.json", metadata)

    summary_lines = [
        "# BASARA Foundry Release Audit — Bootstrap v0.1",
        "",
        f"- Status: **{metadata['status']}**",
        f"- Release pass: **NO**",
        f"- Files hashed: **{len(files)}**",
        f"- ARC members inventoried through canonical safe_arc: **{len(members)}**",
        f"- rTexture providers inventoried: **{len(textures)}**",
        f"- Unresolved/blocking rows: **{len(unresolved)}**",
        "",
        "## Implemented",
        "",
        "- Current-live file hash census",
        "- ARC member inventory using pinned safe_arc.py",
        "- Existing Resource Ownership Analyzer orchestration",
        "- Recovered XET metadata/decode census for supported formats, with 0x15 intercepted and quarantined",
        "- Divergent-provider extraction",
        "- Explicit unresolved queue",
        "- Dependency/tool hash binding",
        "",
        "## Still required before this auditor can ever exit 0",
        "",
        "- texture semantic visual classification + 0x15 fixture resolution",
        "- control-aware GSM/FIM message census",
        "- PAM/media census",
        "- loose/XMB/trophy/platform semantic census",
        "- Donor Matcher V5.1 sweep",
        "- final runtime acceptance merge",
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
        "unresolved_count": len(unresolved),
        "out": str(outdir),
    }, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
