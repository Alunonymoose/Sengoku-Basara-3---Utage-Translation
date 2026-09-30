from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_LIVE = Path(r"E:\Utage Patching New")
ENG_PREFIX = "PS3_GAME/USRDIR/nativePS3/rom/eng/"


def normalize_live_rel(target: str, live_root: Path) -> str:
    raw = target.replace("\\", "/").strip()
    p = Path(target)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(live_root.resolve()).as_posix()
        except Exception:
            return raw
    if raw.lower().startswith("rom/eng/"):
        return ENG_PREFIX + raw[len("rom/eng/"):]
    if raw.lower().startswith(ENG_PREFIX.lower()):
        return raw
    return ENG_PREFIX + raw.lstrip("/")


def eng_arc_rel(live_rel: str) -> str | None:
    p = live_rel.replace("\\", "/")
    if p.lower().startswith(ENG_PREFIX.lower()):
        return p[len(ENG_PREFIX):]
    return None


def impact(
    db_path: Path,
    live_root: Path,
    targets: list[str],
    detail_limit: int = 12,
) -> dict[str, Any]:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    results = []
    for target in targets:
        live_rel = normalize_live_rel(target, live_root)
        arc_rel = eng_arc_rel(live_rel)

        signoff_rows = db.execute(
            """
            SELECT s.name,s.scope,s.status,s.reason,sf.live_rel_path
            FROM signoff_files sf
            JOIN signoffs s ON s.id=sf.signoff_id
            WHERE lower(sf.live_rel_path)=lower(?)
            ORDER BY s.name
            """,
            (live_rel,),
        ).fetchall()

        file_row = None
        resources = []
        shared_payloads = []
        same_name_owners = []
        shared_payload_count = 0
        same_name_owner_count = 0

        if arc_rel is not None:
            file_row = db.execute(
                "SELECT id,rel_path,size,sha256,is_arc FROM files WHERE role='ENG' AND lower(rel_path)=lower(?)",
                (arc_rel,),
            ).fetchone()
            if file_row:
                resources = db.execute(
                    """
                    SELECT id,member_index,name,kind,raw_sha256,
                           printf('0x%08X',type_hash) type_hash,
                           xet_width,xet_height,xet_format
                    FROM v_resources
                    WHERE role='ENG' AND lower(arc_path)=lower(?)
                    ORDER BY member_index
                    """,
                    (arc_rel,),
                ).fetchall()

                seen_payloads = set()
                seen_names = set()
                for r in resources:
                    sha = r["raw_sha256"]
                    if sha not in seen_payloads:
                        owners = db.execute(
                            """
                            SELECT role,arc_path,member_index,name
                            FROM v_resources
                            WHERE raw_sha256=? AND NOT (role='ENG' AND lower(arc_path)=lower(?))
                            ORDER BY role,arc_path,member_index
                            LIMIT 20
                            """,
                            (sha, arc_rel),
                        ).fetchall()
                        if owners:
                            shared_payload_count += 1
                            if len(shared_payloads) < detail_limit:
                                shared_payloads.append({
                                    "raw_sha256": sha,
                                    "source_member": {"index": r["member_index"], "name": r["name"]},
                                    "other_owners": [dict(x) for x in owners],
                                })
                        seen_payloads.add(sha)

                    name_key = str(r["name"]).lower()
                    if name_key not in seen_names:
                        owners = db.execute(
                            """
                            SELECT role,arc_path,member_index,name,raw_sha256
                            FROM v_resources
                            WHERE name_lower=? AND NOT (role='ENG' AND lower(arc_path)=lower(?))
                            ORDER BY role,arc_path,member_index
                            LIMIT 20
                            """,
                            (name_key, arc_rel),
                        ).fetchall()
                        if owners:
                            same_name_owner_count += 1
                            if len(same_name_owners) < detail_limit:
                                same_name_owners.append({
                                    "name": r["name"],
                                    "source_member": r["member_index"],
                                    "other_owners": [dict(x) for x in owners],
                                })
                        seen_names.add(name_key)

        results.append({
            "input": target,
            "live_rel_path": live_rel,
            "eng_arc_path": arc_rel,
            "indexed_file": dict(file_row) if file_row else None,
            "resource_count": len(resources),
            "signoffs_that_would_become_stale": [dict(x) for x in signoff_rows],
            "risk_summary": {
                "certified_file": bool(signoff_rows),
                "shared_payload_count": shared_payload_count,
                "same_name_owner_count": same_name_owner_count,
                "detail_limit": detail_limit,
            },
            "shared_payload_examples": shared_payloads,
            "same_name_owner_examples": same_name_owners,
            "details_truncated": {
                "shared_payloads": shared_payload_count > len(shared_payloads),
                "same_name_owners": same_name_owner_count > len(same_name_owners),
            },
        })

    db.close()
    return {
        "schema": "BASARA_FOUNDRY_CHANGE_IMPACT_V1",
        "db": str(db_path),
        "live_root": str(live_root),
        "targets": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pre-mutation impact report: sign-offs and duplicate/related resource owners"
    )
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--live-root", default=str(DEFAULT_LIVE))
    ap.add_argument("--db")
    ap.add_argument("--detail-limit", type=int, default=12)
    args = ap.parse_args()
    live = Path(args.live_root)
    db = Path(args.db) if args.db else live / ".foundry" / "cache" / "foundry_graph.sqlite"
    print(json.dumps(
        impact(db, live, args.targets, max(0, args.detail_limit)),
        indent=2, ensure_ascii=False
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
