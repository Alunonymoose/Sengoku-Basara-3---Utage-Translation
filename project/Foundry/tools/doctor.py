from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FOUNDRY_ROOT = HERE.parent
PROJECT_ROOT = FOUNDRY_ROOT.parent
sys.path.insert(0, str(HERE))

import foundry_graph as fg

DEFAULT_LIVE = Path(r"E:\Utage Patching New")
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.I)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def make_check(name: str, status: str, summary: str, details: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "status": status, "summary": summary}
    if details is not None:
        row["details"] = details
    return row


def derive_overall(checks: list[dict[str, Any]]) -> str:
    states = {str(c.get("status", "")).upper() for c in checks}
    if "FAIL" in states:
        return "FAIL"
    if "WARN" in states:
        return "WARN"
    return "PASS"


def validate_oracle_lock(data: dict[str, Any] | None) -> tuple[str, str, dict[str, Any]]:
    if not data:
        return "FAIL", "external-oracle lock is missing or unreadable", {}
    rows = data.get("oracles")
    if not isinstance(rows, list) or not rows:
        return "FAIL", "external-oracle lock has no pinned oracles", {}
    bad = []
    names = set()
    for row in rows:
        name = str(row.get("name", "")).strip()
        commit = str(row.get("commit", "")).strip()
        if not name or not HEX40.match(commit):
            bad.append({"name": name, "commit": commit})
        if name:
            names.add(name)
    required = {"RPCS3", "REvilLib", "Kuriimu2", "DirectXTex", "Compressonator", "bcdec", "vgmstream"}
    missing = sorted(required - names)
    if bad or missing:
        return "FAIL", "oracle lock has invalid/missing pins", {"bad": bad, "missing": missing}
    return "PASS", f"{len(rows)} external oracles pinned to exact commits", {"count": len(rows)}


def git_state(repo: Path) -> dict[str, Any]:
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        return {"available": False}
    def run(*args: str) -> str:
        p = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True, capture_output=True, check=False
        )
        return (p.stdout or p.stderr).strip()
    return {
        "available": True,
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "HEAD"),
        "porcelain": run("status", "--porcelain"),
    }


def live_role_freshness(graph: fg.FoundryGraph, role: str, root: Path, detail_limit: int = 20) -> dict[str, Any]:
    rows = graph.db.execute(
        "SELECT rel_path,abs_path,size,mtime_ns FROM files WHERE role=? ORDER BY rel_path",
        (role,),
    ).fetchall()
    indexed = {str(r["rel_path"]): r for r in rows}
    current = {}
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    rel = p.resolve().relative_to(root.resolve()).as_posix()
                    current[rel] = p
                except Exception:
                    continue

    missing = sorted(set(indexed) - set(current))
    new = sorted(set(current) - set(indexed))
    changed = []
    for rel in sorted(set(indexed) & set(current)):
        row = indexed[rel]
        st = current[rel].stat()
        if int(row["size"]) != st.st_size or int(row["mtime_ns"]) != st.st_mtime_ns:
            changed.append(rel)

    return {
        "role": role,
        "root": str(root),
        "indexed_files": len(indexed),
        "current_files": len(current),
        "fresh": not missing and not new and not changed,
        "missing_count": len(missing),
        "new_count": len(new),
        "changed_count": len(changed),
        "missing_examples": missing[:detail_limit],
        "new_examples": new[:detail_limit],
        "changed_examples": changed[:detail_limit],
    }


def run_doctor(live_root: Path = DEFAULT_LIVE) -> dict[str, Any]:
    foundry_dir = live_root / ".foundry"
    checks: list[dict[str, Any]] = []

    current_path = foundry_dir / "PROJECT_CURRENT.json"
    current = load_json(current_path)
    if not current:
        checks.append(make_check("project-current", "FAIL", "PROJECT_CURRENT.json missing or unreadable"))
        current = {}
    else:
        checks.append(make_check("project-current", "PASS", "current authority file is readable"))

    graph_status_path = foundry_dir / "FOUNDRY_GRAPH_STATUS.json"
    graph_status = load_json(graph_status_path)
    db_path = foundry_dir / "cache" / "foundry_graph.sqlite"
    graph = None
    if not graph_status or not db_path.exists():
        checks.append(make_check("foundry-graph", "FAIL", "graph status/database missing; run foundry build"))
    else:
        try:
            graph = fg.FoundryGraph(db_path, live_root)
            actual_fp = graph.fingerprint()
            recorded_fp = graph_status.get("fingerprint")
            if actual_fp != recorded_fp:
                checks.append(make_check(
                    "foundry-graph", "FAIL",
                    "database fingerprint does not match FOUNDRY_GRAPH_STATUS.json",
                    {"actual": actual_fp, "recorded": recorded_fp}
                ))
            else:
                eng = graph_status.get("roles", {}).get("ENG", {})
                parse_errors = int(eng.get("parse_errors") or 0)
                state = "FAIL" if parse_errors else "PASS"
                checks.append(make_check(
                    "foundry-graph", state,
                    f"graph fingerprint matches; ENG parse errors={parse_errors}",
                    {"fingerprint": actual_fp, "eng": eng}
                ))
        except Exception as exc:
            checks.append(make_check("foundry-graph", "FAIL", f"graph could not be opened: {exc!r}"))

    if graph is not None:
        eng_root = live_root / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
        fresh = live_role_freshness(graph, "ENG", eng_root)
        checks.append(make_check(
            "graph-live-freshness",
            "PASS" if fresh["fresh"] else "FAIL",
            (
                "ENG graph matches current live file set/size/mtime"
                if fresh["fresh"]
                else f"ENG graph is stale: {fresh['changed_count']} changed, "
                     f"{fresh['new_count']} new, {fresh['missing_count']} missing"
            ),
            fresh,
        ))

    if graph is not None:
        try:
            signoffs = graph.evaluate_signoffs(update_db=True)
            stale = [s for s in signoffs if s.get("status") != "VALID"]
            checks.append(make_check(
                "signoffs",
                "FAIL" if stale else "PASS",
                f"{len(signoffs) - len(stale)}/{len(signoffs)} machine sign-offs valid",
                {"stale": stale, "all": signoffs}
            ))
        except Exception as exc:
            checks.append(make_check("signoffs", "FAIL", f"sign-off evaluation failed: {exc!r}"))

    tools = current.get("canonical_tools", {}) if isinstance(current, dict) else {}
    tool_rows = []
    tool_fail = []
    for key, spec in tools.items():
        path = Path(str(spec.get("path", "")))
        expected = str(spec.get("sha256", "")).lower()
        if not path.exists():
            row = {"tool": key, "path": str(path), "status": "MISSING"}
            tool_fail.append(row)
        else:
            actual = sha256_file(path)
            ok = bool(expected) and actual == expected
            row = {
                "tool": key, "path": str(path), "status": "OK" if ok else "HASH_MISMATCH",
                "expected": expected, "actual": actual
            }
            if not ok:
                tool_fail.append(row)
        tool_rows.append(row)
    if tools:
        checks.append(make_check(
            "canonical-tools", "FAIL" if tool_fail else "PASS",
            f"{len(tool_rows) - len(tool_fail)}/{len(tool_rows)} canonical tool hashes match",
            tool_rows
        ))
    else:
        checks.append(make_check("canonical-tools", "WARN", "PROJECT_CURRENT has no canonical tool pins"))

    snapshot = current.get("snapshot", {}) if isinstance(current, dict) else {}
    snap_status = str(snapshot.get("status", "UNKNOWN")).upper()
    if snap_status == "CLEAN":
        checks.append(make_check("snapshot", "PASS", "project snapshot is clean/current"))
    elif snap_status == "DIRTY":
        checks.append(make_check(
            "snapshot", "WARN",
            f"historical snapshot is dirty ({snapshot.get('newer_live_files', '?')} newer live files); exact live bytes remain authority"
        ))
    else:
        checks.append(make_check("snapshot", "WARN", f"snapshot state is {snap_status}"))

    canon_repo = Path(str(current.get("canon_repo", {}).get("path", ""))) if current else Path()
    if str(canon_repo) and canon_repo.exists():
        gs = git_state(canon_repo)
        expected_branch = str(current.get("canon_repo", {}).get("branch", ""))
        dirty = bool(gs.get("porcelain"))
        wrong_branch = bool(expected_branch and gs.get("branch") != expected_branch)
        state = "WARN" if dirty or wrong_branch else "PASS"
        checks.append(make_check(
            "canon-worktree", state,
            f"branch={gs.get('branch')} dirty={dirty}",
            {"expected_branch": expected_branch, **gs}
        ))
    else:
        checks.append(make_check("canon-worktree", "WARN", "canonical Git worktree unavailable"))

    registry = load_json(foundry_dir / "AGENT_WORKTREES.json")
    if registry and isinstance(registry.get("worktrees"), dict):
        gpt = registry["worktrees"].get("gpt", {})
        registered_path = Path(str(gpt.get("path", "")))
        actual = git_state(registered_path) if registered_path.exists() else {"available": False}
        mismatches = []
        if actual.get("available"):
            if gpt.get("branch") and gpt.get("branch") != actual.get("branch"):
                mismatches.append("branch")
            if gpt.get("head") and gpt.get("head") != actual.get("head"):
                mismatches.append("head")
        else:
            mismatches.append("path")
        checks.append(make_check(
            "agent-worktree-registry",
            "WARN" if mismatches else "PASS",
            (
                "GPT worktree registry matches the actual worktree"
                if not mismatches
                else "GPT worktree registry is stale: " + ", ".join(mismatches)
            ),
            {"registered": gpt, "actual": actual, "mismatches": mismatches},
        ))
    else:
        checks.append(make_check("agent-worktree-registry", "WARN", "AGENT_WORKTREES.json missing or unreadable"))

    oracle_path = FOUNDRY_ROOT / "third_party" / "ORACLES.lock.json"
    ostate, osummary, odetails = validate_oracle_lock(load_json(oracle_path))
    checks.append(make_check("external-oracles", ostate, osummary, odetails))

    runtime_path = foundry_dir / "runtime" / "RUNTIME_ACCEPTANCE_CURRENT.json"
    runtime = load_json(runtime_path)
    current_fp = graph_status.get("fingerprint") if graph_status else None
    if not runtime:
        checks.append(make_check("runtime-acceptance", "WARN", "runtime acceptance matrix is not bound"))
    else:
        candidate = runtime.get("candidate", {})
        bound_fp = candidate.get("live_root_sha256")
        rows = runtime.get("rows", [])
        statuses: dict[str, int] = {}
        for row in rows:
            key = str(row.get("final_status", "UNKNOWN"))
            statuses[key] = statuses.get(key, 0) + 1
        if current_fp and bound_fp != current_fp:
            checks.append(make_check(
                "runtime-acceptance", "WARN",
                "runtime matrix is bound to an older graph fingerprint",
                {"bound": bound_fp, "current": current_fp, "row_statuses": statuses}
            ))
        else:
            checks.append(make_check(
                "runtime-acceptance", "PASS",
                "runtime matrix is bound to the current graph fingerprint",
                {"row_statuses": statuses}
            ))

    hygiene = load_json(foundry_dir / "ROOT_HYGIENE.json")
    if hygiene:
        hstatus = str(hygiene.get("status", "UNKNOWN")).upper()
        if hstatus in {"PASS", "OK", "CLEAN"}:
            checks.append(make_check("root-hygiene", "PASS", "active-root hygiene report is clean"))
        else:
            checks.append(make_check("root-hygiene", "WARN", f"active-root hygiene state is {hstatus}", hygiene))
    else:
        checks.append(make_check("root-hygiene", "WARN", "ROOT_HYGIENE.json missing"))

    if graph is not None:
        graph.close()

    overall = derive_overall(checks)
    result = {
        "schema": "BASARA_FOUNDRY_PROJECT_HEALTH_V1",
        "generated_at": utcnow(),
        "live_root": str(live_root),
        "overall": overall,
        "checks": checks,
    }
    out = foundry_dir / "PROJECT_HEALTH.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["output"] = str(out)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Whole-project BASARA Foundry health gate")
    ap.add_argument("--live-root", default=str(DEFAULT_LIVE))
    ap.add_argument("--strict", action="store_true", help="return non-zero for WARN as well as FAIL")
    args = ap.parse_args()
    result = run_doctor(Path(args.live_root))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["overall"] == "FAIL":
        return 2
    if args.strict and result["overall"] == "WARN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
