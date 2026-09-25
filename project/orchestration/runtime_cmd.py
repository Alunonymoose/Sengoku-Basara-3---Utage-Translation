from __future__ import annotations
import json
from pathlib import Path

from core import atomic_json, sha256_file, utc_now
from db import connect_db
from resolver import resolve_snapshot


def _snapshot_identity(snapshot):
    db=resolve_snapshot(snapshot); conn=connect_db(db)
    meta={r["key"]:json.loads(r["value"]) for r in conn.execute("SELECT key,value FROM metadata")}
    eboots=[dict(r) for r in conn.execute("SELECT path,sha256 FROM files WHERE upper(path) LIKE '%EBOOT.BIN' OR upper(path) LIKE '%EBOOT.ELF' ORDER BY path")]
    conn.close()
    return meta,eboots


def runtime_init_command(args)->int:
    meta,eboots=_snapshot_identity(args.snapshot)
    matrix=json.loads(Path(args.template).read_text(encoding="utf-8"))
    sid=meta["snapshot_id"]
    matrix["candidate"]={"id":args.candidate_id or f"SNAPSHOT_{sid[:12]}","live_root_sha256":sid,
                         "eboot_sha256":eboots[0]["sha256"] if len(eboots)==1 else None,"created_utc":utc_now()}
    matrix["candidate"]["eboot_candidates"]=eboots
    for row in matrix.get("rows",[]):
        row["final_status"]="NOT_TESTED"; row["build_root_sha256"]=None
        row["screenshot_or_video_evidence"]=[]; row["rpcs3_log_evidence"]=[]
        row.pop("evidence_hashes",None)
    out=Path(args.out); atomic_json(out,matrix)
    print(json.dumps({"out":str(out.resolve()),"candidate":matrix["candidate"],"rows":len(matrix.get("rows",[]))},indent=2))
    return 0


def runtime_record_command(args)->int:
    path=Path(args.matrix).resolve(); matrix=json.loads(path.read_text(encoding="utf-8"))
    rows=[r for r in matrix.get("rows",[]) if r.get("id")==args.row]
    if len(rows)!=1: raise SystemExit(f"Expected exactly one runtime row {args.row!r}; found {len(rows)}")
    row=rows[0]; evidence=[]; screenshots=[]; logs=[]
    for item in args.evidence or []:
        p=Path(item).resolve()
        if not p.is_file(): raise SystemExit(f"Evidence file missing: {p}")
        screenshots.append(str(p)); evidence.append({"kind":"screenshot_or_video","path":str(p),"sha256":sha256_file(p)})
    for item in args.log or []:
        p=Path(item).resolve()
        if not p.is_file(): raise SystemExit(f"RPCS3 log missing: {p}")
        logs.append(str(p)); evidence.append({"kind":"rpcs3_log","path":str(p),"sha256":sha256_file(p)})
    if args.status=="PASS" and not evidence: raise SystemExit("PASS requires at least one hashed evidence file")
    row["final_status"]=args.status
    row["build_root_sha256"]=matrix.get("candidate",{}).get("live_root_sha256") if args.status=="PASS" else None
    row["screenshot_or_video_evidence"]=screenshots
    row["rpcs3_log_evidence"]=logs
    row["evidence_hashes"]=evidence
    if args.notes is not None: row["notes"]=args.notes
    row["recorded_utc"]=utc_now()
    atomic_json(path,matrix); print(json.dumps(row,indent=2)); return 0


def runtime_verify_evidence_command(args)->int:
    matrix=json.loads(Path(args.matrix).read_text(encoding="utf-8")); errors=[]; checked=0
    for row in matrix.get("rows",[]):
        for ev in row.get("evidence_hashes",[]) or []:
            p=Path(ev.get("path",""))
            if not p.is_file(): errors.append({"row":row.get("id"),"path":str(p),"reason":"missing"}); continue
            checked+=1; actual=sha256_file(p)
            if actual!=ev.get("sha256"): errors.append({"row":row.get("id"),"path":str(p),"reason":"sha256","expected":ev.get("sha256"),"actual":actual})
        if row.get("final_status")=="PASS":
            if row.get("build_root_sha256")!=matrix.get("candidate",{}).get("live_root_sha256"):
                errors.append({"row":row.get("id"),"reason":"candidate_binding"})
            if not (row.get("evidence_hashes") or []):
                errors.append({"row":row.get("id"),"reason":"PASS_without_hashed_evidence"})
    result={"matrix":str(Path(args.matrix).resolve()),"checked_evidence":checked,"valid":not errors,"errors":errors}
    print(json.dumps(result,indent=2)); return 0 if not errors else 6
