from __future__ import annotations
import json
from pathlib import Path
from core import RECIPE_SCHEMA,atomic_json,canonical_internal_path,sha256_file,utc_now
from db import connect_db
from resolver import resolve_snapshot


def recipe_new_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); sid=json.loads(conn.execute("SELECT value FROM metadata WHERE key='snapshot_id'").fetchone()[0]); canonical=canonical_internal_path(args.resource); th=int(args.type_hash,0)
    rows=[dict(r) for r in conn.execute("""SELECT f.path arc_path,f.sha256 arc_sha256,r.member_index,r.raw_sha256,r.stored_sha256,r.actual_raw_size,r.type_hex,r.canonical_path FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id WHERE r.type_hash=? AND r.canonical_path=? ORDER BY f.path,r.member_index""",(th,canonical))]; conn.close()
    if not rows: raise SystemExit("No exact typed/path identity in snapshot")
    cpath=Path(args.candidate) if args.candidate else None; chash=sha256_file(cpath) if cpath and cpath.is_file() else None
    recipe={"schema":RECIPE_SCHEMA,"schema_version":1,"recipe_id":args.recipe_id,"created_utc":utc_now(),"source_snapshot_id":sid,"identity":{"type_hash":f"0x{th:08X}","canonical_path":canonical},"providers":rows,"candidate":{"path":args.candidate,"sha256":chash},"approval":{"status":"PENDING","approved_candidate_sha256":None,"evidence":[]},"build":{"encoder":args.encoder,"edit_mask_sha256":None,"expected_output_raw_sha256":None,"expected_output_arc_sha256":{},"notes":None},"runtime":{"status":"NOT_TESTED","evidence":[]}}
    out=Path(args.out); atomic_json(out,recipe); print(str(out.resolve())); return 0


def recipe_validate_command(args)->int:
    rp=Path(args.recipe); recipe=json.loads(rp.read_text(encoding="utf-8")); errors=[]
    if recipe.get("schema")!=RECIPE_SCHEMA: errors.append("wrong schema")
    cpath=recipe.get("candidate",{}).get("path"); recorded=recipe.get("candidate",{}).get("sha256")
    if cpath:
        p=(rp.parent/cpath).resolve() if not Path(cpath).is_absolute() else Path(cpath)
        if p.is_file() and recorded and sha256_file(p)!=recorded: errors.append("candidate differs from recipe candidate.sha256")
    if recipe.get("approval",{}).get("status")=="APPROVED":
        approved=recipe.get("approval",{}).get("approved_candidate_sha256")
        if not approved: errors.append("APPROVED recipe missing approved_candidate_sha256")
        if cpath:
            p=(rp.parent/cpath).resolve() if not Path(cpath).is_absolute() else Path(cpath)
            if p.is_file() and approved and sha256_file(p)!=approved: errors.append(f"candidate hash changed: approved={approved} actual={sha256_file(p)}")
            elif not p.is_file() and args.require_candidate: errors.append(f"candidate missing: {p}")
    if args.snapshot:
        conn=connect_db(resolve_snapshot(args.snapshot)); sid=json.loads(conn.execute("SELECT value FROM metadata WHERE key='snapshot_id'").fetchone()[0])
        if sid!=recipe.get("source_snapshot_id"): errors.append(f"snapshot mismatch: recipe={recipe.get('source_snapshot_id')} current={sid}")
        for provider in recipe.get("providers",[]):
            row=conn.execute("SELECT sha256 FROM files WHERE path=?",(provider["arc_path"],)).fetchone()
            if row is None: errors.append(f"provider missing from snapshot: {provider['arc_path']}")
            elif row[0]!=provider["arc_sha256"]: errors.append(f"provider hash changed in snapshot: {provider['arc_path']}")
        conn.close()
    print(json.dumps({"recipe":str(rp),"valid":not errors,"errors":errors},indent=2)); return 0 if not errors else 4
