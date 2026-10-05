from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(r"E:\Utage Patching New\.foundry\cache\foundry_graph.sqlite")
MODES = {"closeout", "risk", "smallest"}


def valid_scopes(db: sqlite3.Connection) -> list[str]:
    rows = db.execute("SELECT scope FROM signoffs WHERE status='VALID'").fetchall()
    prefix = "PS3_GAME/USRDIR/nativePS3/rom/eng/"
    out = []
    for (scope,) in rows:
        s = str(scope).replace("\\", "/")
        if s.lower().startswith(prefix.lower()):
            out.append(s[len(prefix):].rstrip("/").lower())
    return out


def signed_folder(folder: str, scopes: list[str]) -> bool:
    f = folder.lower().strip("/")
    return any(f == s or f.startswith(s + "/") or s.startswith(f + "/") for s in scopes)


def rank_work(db_path: Path, limit: int = 15, mode: str = "closeout") -> dict:
    if mode not in MODES:
        raise ValueError(f"unsupported mode {mode!r}")

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    scopes = valid_scopes(db)

    folders = {}
    file_rows = db.execute(
        "SELECT rel_path,size,is_arc FROM files WHERE role='ENG' ORDER BY rel_path"
    ).fetchall()
    for row in file_rows:
        rel = str(row["rel_path"]).replace("\\", "/")
        folder = rel.split("/", 1)[0] if "/" in rel else "_ROOT"
        x = folders.setdefault(folder, {
            "folder": folder,
            "bytes": 0,
            "files": 0,
            "arcs": 0,
            "textures": 0,
            "messages": 0,
            "custom_textures": 0,
            "jpn_exact_no_sh": 0,
            "runtime_arcs": 0,
            "runtime_open_count": 0,
            "risk_score": 0,
        })
        x["bytes"] += int(row["size"])
        x["files"] += 1
        x["arcs"] += int(row["is_arc"] or 0)

    resource_rows = db.execute(
        """
        SELECT r.arc_path,r.kind,c.jpn_exact,c.sh_exact,
               COALESCE(ro.open_count,0) runtime_open_count
        FROM v_resources r
        LEFT JOIN comparisons c ON c.resource_id=r.id
        LEFT JOIN runtime_opens ro
          ON lower(replace('rom/eng/' || r.arc_path,'/','\\'))=ro.rel_path
        WHERE r.role='ENG'
        """
    ).fetchall()

    runtime_arcs = set()
    for row in resource_rows:
        arc = str(row["arc_path"]).replace("\\", "/")
        folder = arc.split("/", 1)[0] if "/" in arc else "_ROOT"
        if folder not in folders:
            continue
        x = folders[folder]
        kind = str(row["kind"])
        if kind == "texture":
            x["textures"] += 1
            if row["jpn_exact"] == 1 and row["sh_exact"] != 1:
                x["jpn_exact_no_sh"] += 1
                x["risk_score"] += 40
            elif row["jpn_exact"] == 0 and row["sh_exact"] != 1:
                x["custom_textures"] += 1
                x["risk_score"] += 15
            elif row["sh_exact"] == 1:
                x["risk_score"] -= 4
        elif kind in {"message", "message-map", "charset", "font-map"}:
            x["messages"] += 1
            if row["jpn_exact"] == 1 and row["sh_exact"] != 1:
                x["risk_score"] += 8

        ro = int(row["runtime_open_count"] or 0)
        if ro:
            runtime_arcs.add((folder, arc))
            x["runtime_open_count"] += ro

    for folder, arc in runtime_arcs:
        folders[folder]["runtime_arcs"] += 1

    ranked = []
    for x in folders.values():
        if signed_folder(x["folder"], scopes):
            continue

        mib = x["bytes"] / (1024 * 1024)
        runtime_bonus = min(50.0, math.log2(1 + x["runtime_open_count"]) * 6.0)
        positive_risk = max(0.0, float(x["risk_score"]))
        raw_value = positive_risk + runtime_bonus + 10.0

        # "closeout" intentionally rewards finishing a useful, bounded folder.
        # It prevents enormous families such as id/msg from always dominating.
        closeout_effort = 1.0 + (1.5 * max(1, x["arcs"])) + (0.60 * mib)
        closeout_priority = raw_value / closeout_effort

        # "risk" ignores boundedness and surfaces the largest absolute remaining risk.
        risk_priority = raw_value

        x["mib"] = round(mib, 3)
        x["closeout_priority"] = round(closeout_priority, 3)
        x["risk_priority"] = round(risk_priority, 3)
        x["reason"] = (
            f"{x['jpn_exact_no_sh']} JPN-identical/no-SH textures; "
            f"{x['custom_textures']} custom/Utage textures; "
            f"{x['runtime_arcs']} runtime-seen ARCs"
        )
        ranked.append(x)

    if mode == "closeout":
        ranked.sort(
            key=lambda r: (
                -r["closeout_priority"],
                -r["runtime_arcs"],
                r["arcs"],
                r["bytes"],
                r["folder"],
            )
        )
    elif mode == "risk":
        ranked.sort(
            key=lambda r: (
                -r["risk_priority"],
                -r["jpn_exact_no_sh"],
                -r["custom_textures"],
                r["bytes"],
                r["folder"],
            )
        )
    else:
        ranked.sort(key=lambda r: (r["bytes"], r["arcs"], -r["risk_priority"], r["folder"]))

    db.close()
    return {
        "db": str(db_path),
        "mode": mode,
        "valid_signoff_scopes_excluded": scopes,
        "candidate_folders": len(ranked),
        "next": ranked[:limit],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank the next highest-value unsigned Foundry work")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--mode", choices=sorted(MODES), default="closeout")
    args = ap.parse_args()
    print(json.dumps(rank_work(Path(args.db), args.limit, args.mode), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
