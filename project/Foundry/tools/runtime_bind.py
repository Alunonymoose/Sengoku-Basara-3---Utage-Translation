from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE = Path(r"E:\Utage Patching New")
DEFAULT_TEMPLATE = PROJECT / "runtime" / "runtime_acceptance_matrix_2026-09-24.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bind(live_root: Path, template: Path = DEFAULT_TEMPLATE) -> Path:
    graph_status = live_root / ".foundry" / "FOUNDRY_GRAPH_STATUS.json"
    if not graph_status.exists():
        raise FileNotFoundError("Foundry Graph status missing; run foundry build first")
    graph = json.loads(graph_status.read_text(encoding="utf-8"))
    fingerprint = graph.get("fingerprint")
    if not fingerprint:
        raise ValueError("graph fingerprint missing")

    eboot = live_root / "PS3_GAME" / "USRDIR" / "EBOOT.BIN"
    if not eboot.exists():
        raise FileNotFoundError(eboot)

    data = json.loads(template.read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    candidate_id = f"live-{now[:10]}-{fingerprint[:12]}"
    data["candidate"] = {
        "id": candidate_id,
        "live_root_sha256": fingerprint,
        "eboot_sha256": sha256_file(eboot),
        "created_utc": now,
        "identity_note": "live_root_sha256 is the Foundry Graph sorted role/path/file-SHA256 fingerprint",
    }

    for row in data.get("rows", []):
        row["final_status"] = "NOT_TESTED"
        row["build_root_sha256"] = None
        row["screenshot_or_video_evidence"] = []
        row["rpcs3_log_evidence"] = []
        row["notes"] = None

    out = live_root / ".foundry" / "runtime" / "RUNTIME_ACCEPTANCE_CURRENT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Bind runtime acceptance matrix to exact current Foundry Graph build")
    ap.add_argument("--live-root", default=str(DEFAULT_LIVE))
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    args = ap.parse_args()
    out = bind(Path(args.live_root), Path(args.template))
    data = json.loads(out.read_text(encoding="utf-8"))
    print(json.dumps({"matrix": str(out), "candidate": data["candidate"], "rows": len(data.get("rows", []))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
