from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = Path(r"E:\Utage Patching New\.foundry\cache\foundry_graph.sqlite")
DEFAULT_OUT = Path(r"E:\Utage Patching New\.foundry\TEXTURE_TRIAGE.json")


def load_valid_scopes(db: sqlite3.Connection) -> list[str]:
    rows = db.execute("SELECT scope FROM signoffs WHERE status='VALID'").fetchall()
    prefix = "PS3_GAME/USRDIR/nativePS3/rom/eng/"
    scopes = []
    for (scope,) in rows:
        s = scope.replace("\\", "/")
        if s.lower().startswith(prefix.lower()):
            scopes.append(s[len(prefix):].rstrip("/").lower())
    return scopes


def is_signed_off(arc_path: str, scopes: list[str]) -> bool:
    p = arc_path.replace("\\", "/").lower()
    return any(p == s or p.startswith(s + "/") for s in scopes)


def build_queue(db_path: Path, include_signed: bool = False, limit: int = 5000) -> dict:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    scopes = load_valid_scopes(db)

    rows = db.execute(
        """
        SELECT r.id,r.arc_path,r.member_index,r.name,r.raw_sha256,
               r.xet_width,r.xet_height,r.xet_format,r.xet_mips,
               c.jpn_exact,c.sh_exact,
               COALESCE(ro.open_count,0) runtime_open_count
        FROM v_resources r
        LEFT JOIN comparisons c ON c.resource_id=r.id
        LEFT JOIN runtime_opens ro
          ON lower(replace('rom/eng/' || r.arc_path,'/','\\'))=ro.rel_path
        WHERE r.role='ENG' AND r.kind='texture'
        """
    ).fetchall()

    queue = []
    arc_counts = defaultdict(lambda: {"score": 0, "items": 0, "runtime_items": 0})
    folder_counts = defaultdict(lambda: {"score": 0, "items": 0, "arcs": set(), "runtime_items": 0})
    for row in rows:
        d = dict(row)
        signed = is_signed_off(d["arc_path"], scopes)
        if signed and not include_signed:
            continue

        score = 0
        reasons = []
        if d["jpn_exact"] == 1 and d["sh_exact"] != 1:
            score += 40
            reasons.append("JPN_EXACT_NO_SH_DONOR")
        elif d["jpn_exact"] == 0 and d["sh_exact"] != 1:
            score += 15
            reasons.append("CUSTOM_OR_UTAGE")
        elif d["sh_exact"] == 1:
            score -= 20
            reasons.append("OFFICIAL_SH_EXACT")

        if d["runtime_open_count"]:
            score += min(15, 3 + int(d["runtime_open_count"]) // 10)
            reasons.append("RUNTIME_SEEN")

        if d["xet_format"] not in (0x2A, 0x17, 0x19, 0x15, 0x27, None):
            score += 8
            reasons.append("UNCOMMON_FORMAT")

        if score <= 0:
            continue
        d["signed_off_scope"] = signed
        d["score"] = score
        d["reasons"] = reasons
        queue.append(d)
        acc = arc_counts[d["arc_path"]]
        acc["score"] += score
        acc["items"] += 1
        if d["runtime_open_count"]:
            acc["runtime_items"] += 1
        folder = d["arc_path"].replace("\\", "/").split("/", 1)[0] if "/" in d["arc_path"].replace("\\", "/") else "_ROOT"
        facc = folder_counts[folder]
        facc["score"] += score
        facc["items"] += 1
        facc["arcs"].add(d["arc_path"])
        if d["runtime_open_count"]:
            facc["runtime_items"] += 1

    queue.sort(key=lambda x: (-x["score"], -x["runtime_open_count"], x["arc_path"], x["member_index"]))
    queue = queue[:limit]
    arcs = [
        {"arc_path": k, **v}
        for k, v in arc_counts.items()
    ]
    arcs.sort(key=lambda x: (-x["score"], -x["runtime_items"], x["arc_path"]))

    folders = [
        {"folder": k, "score": v["score"], "items": v["items"], "arcs": len(v["arcs"]), "runtime_items": v["runtime_items"]}
        for k, v in folder_counts.items()
    ]
    folders.sort(key=lambda x: (-x["score"], -x["runtime_items"], x["folder"]))

    result = {
        "db": str(db_path),
        "valid_signoff_scopes_excluded": scopes if not include_signed else [],
        "candidate_count": len(queue),
        "arc_count": len(arcs),
        "top_folders": folders,
        "top_arcs": arcs[:200],
        "textures": queue,
    }
    db.close()
    return result


def export(result: dict, json_path: Path, csv_path: Path | None = None):
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if csv_path is None:
        csv_path = json_path.with_suffix(".csv")
    fields = [
        "score","arc_path","member_index","name","runtime_open_count",
        "jpn_exact","sh_exact","xet_width","xet_height","xet_format","reasons","raw_sha256"
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in result["textures"]:
            x = dict(row)
            x["reasons"] = ";".join(x["reasons"])
            w.writerow(x)
    return json_path, csv_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Prioritize live Utage textures for Japanese/ugly/broken visual QA")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--output", default=str(DEFAULT_OUT))
    ap.add_argument("--include-signed", action="store_true")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    result = build_queue(Path(args.db), args.include_signed, args.limit)
    jp, cp = export(result, Path(args.output))
    print(json.dumps({
        "candidate_count": result["candidate_count"],
        "arc_count": result["arc_count"],
        "top_folders": result["top_folders"][:args.top],
        "top_arcs": result["top_arcs"][:args.top],
        "json": str(jp),
        "csv": str(cp),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
