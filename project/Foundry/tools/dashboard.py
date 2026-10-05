from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doctor
import foundry_graph as fg
import next_work
import texture_triage
import translation_memory

DEFAULT_LIVE = Path(r"E:\Utage Patching New")


def runtime_summary(live_root: Path) -> dict[str, Any]:
    path = live_root / ".foundry" / "runtime" / "RUNTIME_ACCEPTANCE_CURRENT.json"
    if not path.exists():
        return {"available": False, "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    blockers = []
    for row in data.get("rows", []):
        status = str(row.get("final_status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
        if status != "PASS":
            blockers.append({
                "id": row.get("id"),
                "family": row.get("family"),
                "status": status,
                "test_route": row.get("test_route"),
            })
    return {
        "available": True,
        "path": str(path),
        "candidate": data.get("candidate"),
        "status_counts": counts,
        "release_ready": not blockers,
        "blockers": blockers,
    }


def tm_summary(live_root: Path) -> dict[str, Any]:
    path = live_root / ".foundry" / "cache" / "translation_memory.sqlite"
    if not path.exists():
        return {
            "available": False,
            "db": str(path),
            "note": "translation memory has not been populated yet",
        }
    tm = translation_memory.TranslationMemory(path)
    try:
        audit = tm.audit()
    finally:
        tm.close()
    audit["available"] = True
    return audit


def top_texture_triage(db_path: Path, limit: int = 20) -> dict[str, Any]:
    result = texture_triage.build_queue(db_path, include_signed=False, limit=5000)
    return {
        "candidate_count": result["candidate_count"],
        "arc_count": result["arc_count"],
        "top_folders": result["top_folders"][:limit],
        "top_arcs": result["top_arcs"][:limit],
        "top_textures": result["textures"][:limit],
    }


def build_dashboard(live_root: Path = DEFAULT_LIVE, refresh: bool = False, top: int = 12) -> dict[str, Any]:
    if refresh:
        fg.build_graph(live_root, include_jpn=True, include_sh=True, verbose=False)

    db_path = fg.default_db(live_root)
    if not db_path.exists():
        raise FileNotFoundError("Foundry Graph missing; run foundry build")

    health = doctor.run_doctor(live_root)
    closeout = next_work.rank_work(db_path, top, "closeout")
    risk = next_work.rank_work(db_path, top, "risk")
    smallest = next_work.rank_work(db_path, top, "smallest")
    texture = top_texture_triage(db_path, top)
    runtime = runtime_summary(live_root)
    tm = tm_summary(live_root)

    graph = fg.FoundryGraph(db_path, live_root)
    try:
        graph_summary = graph.summary()
    finally:
        graph.close()

    result = {
        "schema": "BASARA_FOUNDRY_DASHBOARD_V1",
        "live_root": str(live_root),
        "graph_fingerprint": graph_summary.get("fingerprint"),
        "health": health,
        "signoffs": graph_summary.get("signoffs", []),
        "runtime": runtime,
        "translation_memory": tm,
        "texture_triage": texture,
        "next_closeout": closeout["next"],
        "highest_absolute_risk": risk["next"],
        "smallest_unsigned": smallest["next"],
    }

    foundry_dir = live_root / ".foundry"
    json_path = foundry_dir / "DASHBOARD.json"
    md_path = foundry_dir / "DASHBOARD.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    result["outputs"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def render_markdown(data: dict[str, Any]) -> str:
    health = data["health"]
    lines = [
        "# BASARA Foundry Dashboard",
        "",
        f"Graph fingerprint: {data.get('graph_fingerprint')}",
        f"Project health: **{health.get('overall')}**",
        "",
        "## Health",
        "",
    ]
    for check in health.get("checks", []):
        lines.append(f"- **{check.get('status')}** {check.get('name')} — {check.get('summary')}")

    lines.extend(["", "## Sign-offs", ""])
    for row in data.get("signoffs", []):
        lines.append(f"- **{row.get('status')}** {row.get('name')} — {row.get('scope')}")

    rt = data.get("runtime", {})
    lines.extend(["", "## Runtime acceptance", ""])
    if not rt.get("available"):
        lines.append("- Runtime matrix unavailable.")
    else:
        lines.append(f"- Release ready: **{rt.get('release_ready')}**")
        lines.append(f"- Status counts: {json.dumps(rt.get('status_counts', {}), sort_keys=True)}")
        for row in rt.get("blockers", [])[:12]:
            lines.append(
                f"- {row.get('id')} [{row.get('family')}] — **{row.get('status')}** — {row.get('test_route')}"
            )

    tm = data.get("translation_memory", {})
    lines.extend(["", "## Translation memory", ""])
    if not tm.get("available"):
        lines.append("- Not populated yet.")
    else:
        lines.append(f"- Entries: **{tm.get('entries')}**")
        lines.append(f"- Approved conflicts: **{tm.get('approved_source_conflicts')}**")

    lines.extend(["", "## Best next closeouts", ""])
    for i, row in enumerate(data.get("next_closeout", [])[:10], 1):
        lines.append(
            f"{i}. **{row.get('folder')}** — priority {row.get('closeout_priority')} — "
            f"{row.get('arcs')} ARC(s), {row.get('mib')} MiB — {row.get('reason')}"
        )

    lines.extend(["", "## Highest absolute remaining risk", ""])
    for i, row in enumerate(data.get("highest_absolute_risk", [])[:10], 1):
        lines.append(
            f"{i}. **{row.get('folder')}** — risk {row.get('risk_priority')} — {row.get('reason')}"
        )

    tq = data.get("texture_triage", {})
    lines.extend(["", "## Texture QA queue", ""])
    lines.append(
        f"- Candidates: **{tq.get('candidate_count', 0)}** across **{tq.get('arc_count', 0)}** ARC(s)."
    )
    for row in tq.get("top_arcs", [])[:10]:
        lines.append(
            f"- {row.get('arc_path')} — score {row.get('score')} — "
            f"{row.get('items')} candidate texture(s), {row.get('runtime_items')} runtime-seen"
        )

    lines.extend([
        "",
        "## Rule",
        "",
        "This dashboard is derived state. Exact current live bytes remain production authority.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="One-screen BASARA Foundry project dashboard")
    ap.add_argument("--live-root", default=str(DEFAULT_LIVE))
    ap.add_argument("--refresh", action="store_true", help="refresh the Foundry Graph first")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()
    result = build_dashboard(Path(args.live_root), args.refresh, args.top)
    print(json.dumps({
        "health": result["health"]["overall"],
        "graph_fingerprint": result["graph_fingerprint"],
        "valid_signoffs": sum(s.get("status") == "VALID" for s in result["signoffs"]),
        "signoff_count": len(result["signoffs"]),
        "runtime": result["runtime"].get("status_counts"),
        "translation_conflicts": result["translation_memory"].get("approved_source_conflicts"),
        "next_closeout": result["next_closeout"][:5],
        "top_texture_arcs": result["texture_triage"]["top_arcs"][:5],
        "outputs": result["outputs"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
