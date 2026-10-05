from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

FOUNDRY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = FOUNDRY_ROOT / "third_party" / "ORACLES.lock.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.I)


def load_lock(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("oracles")
    if not isinstance(rows, list):
        raise ValueError("oracle lock missing oracles[]")
    return data


def remote_head(repo: str, timeout: int = 20) -> tuple[str | None, str | None]:
    url = f"https://github.com/{repo}.git"
    try:
        proc = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return None, repr(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None, "git ls-remote returned no HEAD"
    sha = line[0].split()[0]
    if not HEX40.match(sha):
        return None, f"unexpected HEAD: {sha!r}"
    return sha.lower(), None


def audit(path: Path = DEFAULT_LOCK, online: bool = False) -> dict[str, Any]:
    data = load_lock(path)
    rows = []
    bad_pins = 0
    drift = 0
    errors = 0

    for item in data["oracles"]:
        name = str(item.get("name", ""))
        repo = str(item.get("repo", ""))
        pinned = str(item.get("commit", "")).lower()
        pin_ok = bool(repo and HEX40.match(pinned))
        row = {
            "name": name,
            "repo": repo,
            "pinned": pinned,
            "pin_valid": pin_ok,
            "roles": item.get("role", []),
            "adoption": item.get("adoption"),
        }
        if not pin_ok:
            bad_pins += 1

        if online and pin_ok:
            head, error = remote_head(repo)
            row["upstream_head"] = head
            row["online_error"] = error
            row["drift"] = bool(head and head != pinned)
            if row["drift"]:
                drift += 1
            if error:
                errors += 1
        rows.append(row)

    status = "FAIL" if bad_pins else ("WARN" if errors else "PASS")
    return {
        "schema": "BASARA_FOUNDRY_ORACLE_AUDIT_V1",
        "lock": str(path),
        "online": online,
        "status": status,
        "oracle_count": len(rows),
        "invalid_pins": bad_pins,
        "upstream_drift": drift if online else None,
        "online_errors": errors if online else None,
        "oracles": rows,
        "policy": (
            "Upstream drift is informational. Never update a pin or production codec "
            "without reviewing the delta and rerunning relevant fixture/runtime tests."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate pinned external oracles and optionally check upstream HEADs")
    ap.add_argument("--lock", default=str(DEFAULT_LOCK))
    ap.add_argument("--online", action="store_true")
    args = ap.parse_args()
    result = audit(Path(args.lock), args.online)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
