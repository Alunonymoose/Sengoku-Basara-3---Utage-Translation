from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path

DEFAULT_LIVE = Path(r"E:\Utage Patching New")
VALID_STATUS = {"PASS", "FAIL", "BLOCKED", "NOT_TESTED"}
LOG_EXTS = {".log", ".txt", ".gz"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def evidence_ref(path: Path) -> str:
    p = path.resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(p)
    return f"{p} | sha256={sha256_file(p)} | size={p.stat().st_size}"


def record(
    live_root: Path,
    row_id: str,
    status: str,
    evidence: list[Path],
    note: str | None = None,
) -> dict:
    status = status.upper()
    if status not in VALID_STATUS:
        raise ValueError(f"unsupported status {status!r}; expected one of {sorted(VALID_STATUS)}")

    foundry = live_root / ".foundry"
    graph_status_path = foundry / "FOUNDRY_GRAPH_STATUS.json"
    matrix_path = foundry / "runtime" / "RUNTIME_ACCEPTANCE_CURRENT.json"
    if not graph_status_path.exists():
        raise FileNotFoundError("FOUNDRY_GRAPH_STATUS.json missing; run foundry build")
    if not matrix_path.exists():
        raise FileNotFoundError("runtime matrix missing; run foundry runtime-bind")

    graph = json.loads(graph_status_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    graph_fp = graph.get("fingerprint")
    candidate = matrix.get("candidate") or {}
    bound_fp = candidate.get("live_root_sha256")
    if not graph_fp or bound_fp != graph_fp:
        raise RuntimeError(
            "runtime matrix is not bound to the current graph fingerprint; run foundry runtime-bind first"
        )

    row = next((x for x in matrix.get("rows", []) if x.get("id") == row_id), None)
    if row is None:
        ids = [x.get("id") for x in matrix.get("rows", [])]
        raise KeyError(f"unknown runtime row {row_id!r}; known rows: {ids}")

    refs = [evidence_ref(Path(p)) for p in evidence]
    if status == "PASS" and not refs:
        raise ValueError("PASS requires at least one hashed screenshot/video/log evidence file")

    screenshots = []
    logs = []
    for ref, p in zip(refs, evidence):
        suffixes = [s.lower() for s in Path(p).suffixes]
        is_log = any(s in LOG_EXTS for s in suffixes) or "rpcs3" in Path(p).name.lower()
        (logs if is_log else screenshots).append(ref)

    row["final_status"] = status
    row["build_root_sha256"] = graph_fp if status != "NOT_TESTED" else None
    row["screenshot_or_video_evidence"] = screenshots
    row["rpcs3_log_evidence"] = logs
    row["tested_utc"] = utcnow() if status != "NOT_TESTED" else None
    row["notes"] = note

    hist = foundry / "runtime" / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = hist / f"RUNTIME_ACCEPTANCE_BEFORE_{row_id}_{stamp}.json"
    shutil.copy2(matrix_path, backup)

    tmp = matrix_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    os.replace(tmp, matrix_path)

    return {
        "matrix": str(matrix_path),
        "backup": str(backup),
        "row": row_id,
        "status": status,
        "build_root_sha256": row["build_root_sha256"],
        "screenshot_or_video_evidence": screenshots,
        "rpcs3_log_evidence": logs,
        "notes": note,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Record runtime evidence against the exact current Foundry build")
    ap.add_argument("row_id")
    ap.add_argument("status", choices=sorted(VALID_STATUS))
    ap.add_argument("evidence", nargs="*")
    ap.add_argument("--live-root", default=str(DEFAULT_LIVE))
    ap.add_argument("--note")
    args = ap.parse_args()
    result = record(
        Path(args.live_root),
        args.row_id,
        args.status,
        [Path(p) for p in args.evidence],
        args.note,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
