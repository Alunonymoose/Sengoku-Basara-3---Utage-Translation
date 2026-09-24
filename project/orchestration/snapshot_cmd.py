from __future__ import annotations
import json
from pathlib import Path
from core import SCHEMA_VERSION,SNAPSHOT_SCHEMA,atomic_json,canonical_internal_path,canonical_scan_root,find_repo_root,iter_files,load_ownership_module,load_safe_arc,sha256_bytes,sha256_file,tree_hash,utc_now
from db import connect_db,init_db


def snapshot_command(args) -> int:
    scan_root, anchor_root = canonical_scan_root(Path(args.root))
    if not scan_root.is_dir(): raise SystemExit(f"Live root does not exist: {scan_root}")
    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
    safe_arc = load_safe_arc(repo_root)
    ownership = load_ownership_module(repo_root) if args.rpcs3_log else None
    state_root = Path(args.state_dir).resolve() if args.state_dir else anchor_root / ".foundry"
    state_root.mkdir(parents=True,exist_ok=True)
    records=[]; arc_paths=[]
    for path in sorted(iter_files(scan_root,state_root),key=lambda p:p.relative_to(scan_root).as_posix().lower()):
        st=path.stat(); rel=path.relative_to(scan_root).as_posix(); digest=sha256_file(path); kind="arc" if path.suffix.lower()==".arc" else "file"
        records.append({"path":rel,"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":digest,"kind":kind})
        if kind=="arc": arc_paths.append(path)
    sid=tree_hash(records); snapdir=state_root/"snapshots"/sid; snapdir.mkdir(parents=True,exist_ok=True); dbpath=snapdir/"index.sqlite3"
    if dbpath.exists() and not args.force:
        print(str(snapdir/"snapshot.json")); return 0
    if dbpath.exists(): dbpath.unlink()
    conn=connect_db(dbpath); init_db(conn)
    meta={"schema":SNAPSHOT_SCHEMA,"schema_version":SCHEMA_VERSION,"snapshot_id":sid,"live_tree_sha256":sid,"created_utc":utc_now(),"scan_root":str(scan_root),"anchor_root":str(anchor_root),"source_git_commit":args.git_commit,"safe_arc_source_commit":getattr(safe_arc,"SOURCE_COMMIT",None)}
    conn.executemany("INSERT INTO metadata(key,value) VALUES(?,?)",[(k,json.dumps(v)) for k,v in meta.items()])
    file_ids={}
    for rec in records:
        cur=conn.execute("INSERT INTO files(path,size,mtime_ns,sha256,kind) VALUES(?,?,?,?,?)",(rec["path"],rec["size"],rec["mtime_ns"],rec["sha256"],rec["kind"])); file_ids[rec["path"]]=int(cur.lastrowid)
    errors=[]; warnings=[]; resource_count=0
    for path in arc_paths:
        rel=path.relative_to(scan_root).as_posix(); fid=file_ids[rel]
        try:
            entries=safe_arc.parse_arc(path.read_bytes()); alignment=safe_arc.detect_alignment(entries)
            cur=conn.execute("INSERT INTO arcs(file_id,parse_status,version,member_count,alignment,error) VALUES(?,'OK',8,?,?,NULL)",(fid,len(entries),alignment)); aid=int(cur.lastrowid)
            for e in entries:
                internal=e["name"]; canonical=canonical_internal_path(internal)
                conn.execute("""INSERT INTO resources(arc_id,member_index,internal_path,canonical_path,type_hash,type_hex,flags,codec,compressed_size,declared_raw_size,actual_raw_size,data_offset,stored_sha256,raw_sha256,warning) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (aid,e["index"],internal,canonical,e["type_hash"],f"0x{e['type_hash']:08X}",e["flags"],e["codec"],e["compressed_size"],e["raw_size"],len(e["raw"]),e["payload_offset"],sha256_bytes(e["stored"]),sha256_bytes(e["raw"]),e["warning"]))
                resource_count+=1
                if e["warning"]: warnings.append({"arc":rel,"member_index":e["index"],"internal_path":internal,"warning":e["warning"]})
        except Exception as exc:
            conn.execute("INSERT INTO arcs(file_id,parse_status,error) VALUES(?,'ERROR',?)",(fid,repr(exc))); errors.append({"arc":rel,"error":repr(exc)})
    if args.rpcs3_log:
        log=Path(args.rpcs3_log).resolve(); events=ownership.load_order_from_log(log)
        for row in conn.execute("SELECT a.id,f.path FROM arcs a JOIN files f ON f.id=a.file_id WHERE a.parse_status='OK'"):
            rank=ownership.rank_provider(row["path"],events)
            if rank is not None: conn.execute("INSERT INTO arc_runtime_order VALUES(?,?,?)",(row["id"],rank,str(log)))
        for k,v in [("rpcs3_log",str(log)),("rpcs3_load_events",len(events))]:
            conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)",(k,json.dumps(v))); meta[k]=v
    conn.commit()
    dup=conn.execute("SELECT COUNT(*) FROM provider_groups WHERE provider_count>1").fetchone()[0]
    div=conn.execute("SELECT COUNT(*) FROM provider_groups WHERE provider_count>1 AND payload_variants>1").fetchone()[0]
    ranked=conn.execute("SELECT COUNT(*) FROM arc_runtime_order").fetchone()[0]; conn.close()
    manifest={**meta,"file_count":len(records),"arc_file_count":len(arc_paths),"resource_count":resource_count,"duplicate_provider_groups":dup,"divergent_provider_groups":div,"parse_error_count":len(errors),"warning_count":len(warnings),"runtime_ranked_arcs":ranked,"database":"index.sqlite3","manifest":"files.json"}
    atomic_json(snapdir/"snapshot.json",manifest); atomic_json(snapdir/"files.json",records); atomic_json(snapdir/"parse_errors.json",errors); atomic_json(snapdir/"arc_warnings.json",warnings)
    (state_root/"CURRENT_SNAPSHOT").write_text(sid+"\n",encoding="ascii"); print(json.dumps(manifest,indent=2))
    return 1 if errors and args.fail_on_parse_error else 0
