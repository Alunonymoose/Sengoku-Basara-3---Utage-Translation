from __future__ import annotations
import json
import re
from pathlib import Path
from core import canonical_internal_path,find_repo_root,load_ownership_module,sha256_file
from db import connect_db
from resolver import resolve_snapshot


def query_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); q=canonical_internal_path(args.resource); params=[]; where=[]
    if args.exact: where.append("r.canonical_path=?"); params.append(q)
    else: where.append("(r.canonical_path LIKE ? OR lower(f.path) LIKE ?)"); params += [f"%{q}%",f"%{q}%"]
    if args.type_hash: where.append("r.type_hash=?"); params.append(int(args.type_hash,0))
    rows=[dict(r) for r in conn.execute(f"""SELECT r.type_hex,r.type_hash,r.internal_path,r.canonical_path,r.member_index,r.raw_sha256,r.stored_sha256,r.codec,r.flags,r.actual_raw_size,r.declared_raw_size,r.warning,f.path arc_path,f.sha256 arc_sha256,aro.runtime_rank FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id LEFT JOIN arc_runtime_order aro ON aro.arc_id=a.id WHERE {' AND '.join(where)} ORDER BY r.canonical_path,r.type_hash,f.path,r.member_index""",params)]
    conn.close(); groups={}
    for row in rows: groups.setdefault((row["type_hash"],row["canonical_path"]),[]).append(row)
    out=[]
    for providers in groups.values():
        variants=len({p["raw_sha256"] for p in providers}); ranked=[p for p in providers if p["runtime_rank"] is not None]; effective=min(ranked,key=lambda p:p["runtime_rank"])["arc_path"] if ranked else None
        out.append({"type_hex":providers[0]["type_hex"],"canonical_path":providers[0]["canonical_path"],"provider_count":len(providers),"payload_variants":variants,"status":"DIVERGENT" if variants>1 else ("DUPLICATE_IDENTICAL" if len(providers)>1 else "SINGLE_PROVIDER"),"observed_effective_provider":effective,"providers":providers})
    if args.json: print(json.dumps(out,indent=2))
    else:
        if not out: print("NO_MATCH"); return 2
        for g in out:
            print(f"{g['type_hex']} {g['canonical_path']} :: {g['status']} providers={g['provider_count']} variants={g['payload_variants']} effective={g['observed_effective_provider'] or 'UNKNOWN'}")
            for p in g["providers"]: print(f"  {p['arc_path']}[{p['member_index']}] raw={p['raw_sha256'][:16]} arc={p['arc_sha256'][:16]} codec={p['codec']} runtime_rank={p['runtime_rank']}")
    return 0


def bind_log_command(args)->int:
    db=resolve_snapshot(args.snapshot); repo=Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path(__file__).resolve()); own=load_ownership_module(repo); log=Path(args.rpcs3_log).resolve(); events=own.load_order_from_log(log); conn=connect_db(db); conn.execute("DELETE FROM arc_runtime_order"); ranked=0
    for row in conn.execute("SELECT a.id,f.path FROM arcs a JOIN files f ON f.id=a.file_id WHERE a.parse_status='OK'"):
        rank=own.rank_provider(row["path"],events)
        if rank is not None: conn.execute("INSERT INTO arc_runtime_order VALUES(?,?,?)",(row["id"],rank,str(log))); ranked+=1
    for k,v in [("rpcs3_log",str(log)),("rpcs3_load_events",len(events))]: conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)",(k,json.dumps(v)))
    conn.commit(); conn.close(); print(json.dumps({"rpcs3_log":str(log),"load_events":len(events),"ranked_arcs":ranked},indent=2)); return 0


def hazards_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); out=[]
    for g in conn.execute("SELECT * FROM provider_groups WHERE provider_count>1 AND payload_variants>1 ORDER BY canonical_path,type_hash"):
        ps=[dict(r) for r in conn.execute("""SELECT f.path arc_path,r.member_index,r.raw_sha256,r.stored_sha256,aro.runtime_rank FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id LEFT JOIN arc_runtime_order aro ON aro.arc_id=a.id WHERE r.type_hash=? AND r.canonical_path=? ORDER BY f.path,r.member_index""",(g["type_hash"],g["canonical_path"]))]; ranked=[p for p in ps if p["runtime_rank"] is not None]; effective=min(ranked,key=lambda p:p["runtime_rank"])["arc_path"] if ranked else None
        out.append({"type_hex":g["type_hex"],"canonical_path":g["canonical_path"],"provider_count":g["provider_count"],"payload_variants":g["payload_variants"],"observed_effective_provider":effective,"providers":ps})
    conn.close(); out=out[:args.limit] if args.limit is not None else out; print(json.dumps({"count":len(out),"groups":out},indent=2)); return 0


def verify_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); root=Path(args.root).resolve() if args.root else Path(json.loads(conn.execute("SELECT value FROM metadata WHERE key='scan_root'").fetchone()[0])); missing=[]; mismatches=[]; checked=0
    for row in conn.execute("SELECT path,size,sha256 FROM files ORDER BY path"):
        p=root/row["path"]
        if not p.is_file(): missing.append(row["path"]); continue
        checked+=1; st=p.stat()
        if st.st_size!=row["size"]: mismatches.append({"path":row["path"],"reason":"size","expected":row["size"],"actual":st.st_size}); continue
        actual=sha256_file(p)
        if actual!=row["sha256"]: mismatches.append({"path":row["path"],"reason":"sha256","expected":row["sha256"],"actual":actual})
    conn.close(); result={"root":str(root),"checked":checked,"missing":missing,"mismatches":mismatches,"match":not missing and not mismatches}; print(json.dumps(result,indent=2)); return 0 if result["match"] else 3


def status_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); meta={r["key"]:json.loads(r["value"]) for r in conn.execute("SELECT key,value FROM metadata")}; counts={"files":conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],"arcs_ok":conn.execute("SELECT COUNT(*) FROM arcs WHERE parse_status='OK'").fetchone()[0],"arcs_error":conn.execute("SELECT COUNT(*) FROM arcs WHERE parse_status!='OK'").fetchone()[0],"arcs_with_container_anomalies":conn.execute("SELECT COUNT(*) FROM arcs WHERE container_warning IS NOT NULL").fetchone()[0],"resources":conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0],"duplicate_groups":conn.execute("SELECT COUNT(*) FROM provider_groups WHERE provider_count>1").fetchone()[0],"divergent_groups":conn.execute("SELECT COUNT(*) FROM provider_groups WHERE provider_count>1 AND payload_variants>1").fetchone()[0],"runtime_ranked_arcs":conn.execute("SELECT COUNT(*) FROM arc_runtime_order").fetchone()[0]}; conn.close(); print(json.dumps({"metadata":meta,"counts":counts},indent=2)); return 0


def _route_family(path: str) -> tuple[str,str]:
    p=path.replace("\\","/").lower()
    marker="/rom/"
    i=p.find(marker)
    tail=p[i+len(marker):] if i>=0 else p
    parts=tail.split("/")
    if parts and parts[0] in {"eng","jpn"}:
        route=parts[0]
        if len(parts)==2:
            family=f"{route}/{parts[1]}"
        elif len(parts)>=3:
            family=f"{route}/{parts[1]}"
        else:
            family=route
    else:
        route="other"; family=parts[0] if parts else "other"
    return route,family


def _obvious_backup_name(path: str) -> bool:
    name=Path(path.replace("\\","/")).stem.lower()
    pats=[r"(^|[ _\-])copy($|[ _\-])",r"backup",r"(^|_)bak($|_)",r"pre[_\- ]",r"old($|[_\- ])",r"\(\d+\)$"]
    return any(re.search(p,name) for p in pats)


def _derivative_provider_flags(paths: list[str]) -> set[str]:
    flagged={p for p in paths if _obvious_backup_name(p)}
    by_dir={}
    for p in paths:
        pp=p.replace("\\","/")
        d,n=pp.rsplit("/",1) if "/" in pp else ("",pp)
        stem=Path(n).stem.lower()
        by_dir.setdefault(d,[]).append((p,stem))
    for items in by_dir.values():
        for p,stem in items:
            for q,qstem in items:
                if p==q: continue
                if len(stem)>len(qstem) and (stem.startswith(qstem+"_") or stem.startswith(qstem+" -") or stem.startswith(qstem+" ")):
                    flagged.add(p)
    return flagged


def triage_command(args)->int:
    conn=connect_db(resolve_snapshot(args.snapshot)); groups=[]
    for g in conn.execute("SELECT * FROM provider_groups WHERE provider_count>1 AND payload_variants>1"):
        ps=[dict(r) for r in conn.execute("""SELECT f.path arc_path,r.member_index,r.raw_sha256,r.stored_sha256,aro.runtime_rank
            FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id
            LEFT JOIN arc_runtime_order aro ON aro.arc_id=a.id
            WHERE r.type_hash=? AND r.canonical_path=? ORDER BY f.path,r.member_index""",(g["type_hash"],g["canonical_path"]))]
        paths=[p["arc_path"] for p in ps]; contamination=_derivative_provider_flags(paths)
        active=[p for p in ps if p["arc_path"] not in contamination]
        by_route={}; by_family={}; route_members={}
        for p in active:
            route,family=_route_family(p["arc_path"])
            by_route.setdefault(route,set()).add(p["raw_sha256"])
            by_family.setdefault(family,set()).add(p["raw_sha256"])
            route_members.setdefault(route,[]).append(p)
            p["route"]=route; p["family"]=family; p["tree_role"]="ACTIVE_CANDIDATE"
        for p in ps:
            if p["arc_path"] in contamination:
                route,family=_route_family(p["arc_path"]); p["route"]=route; p["family"]=family; p["tree_role"]="BACKUP_OR_DERIVATIVE"

        route_summary={}; consensus_outliers=[]
        for route,members in sorted(route_members.items()):
            counts={}
            for p in members:
                counts[p["raw_sha256"]]=counts.get(p["raw_sha256"],0)+1
            dominant_hash,dominant_count=max(counts.items(),key=lambda kv:(kv[1],kv[0]))
            total=len(members); fraction=dominant_count/total if total else 0.0
            outliers=[p for p in members if p["raw_sha256"]!=dominant_hash]
            route_summary[route]={
                "provider_count":total,
                "variant_count":len(counts),
                "dominant_raw_sha256":dominant_hash,
                "dominant_count":dominant_count,
                "dominant_fraction":round(fraction,6),
                "outlier_count":len(outliers),
            }
            if len(counts)>1 and fraction>=0.80:
                for p in outliers:
                    consensus_outliers.append({
                        "route":route,
                        "arc_path":p["arc_path"],
                        "member_index":p["member_index"],
                        "raw_sha256":p["raw_sha256"],
                        "dominant_raw_sha256":dominant_hash,
                        "runtime_rank":p["runtime_rank"],
                    })

        ranked=[p for p in active if p["runtime_rank"] is not None]
        effective=min(ranked,key=lambda p:p["runtime_rank"])["arc_path"] if ranked else None
        same_family=[fam for fam,vals in by_family.items() if len(vals)>1]
        same_route=[route for route,vals in by_route.items() if len(vals)>1]
        active_variants=len({p["raw_sha256"] for p in active})

        eng_summary=route_summary.get("eng")
        eng_consensus=(eng_summary is not None and eng_summary["variant_count"]>1 and
                       eng_summary["dominant_fraction"]>=0.80 and eng_summary["outlier_count"]>0)
        if eng_consensus:
            cls="ENG_CONSENSUS_OUTLIER"; score=140
        elif same_family:
            cls="SAME_FAMILY_DIVERGENCE"; score=100
        elif same_route:
            cls="SAME_ROUTE_CROSS_FAMILY_DIVERGENCE"; score=80
        elif set(by_route)=={"eng","jpn"} and all(len(v)==1 for v in by_route.values()):
            cls="EXPECTED_ENG_JPN_DIVERGENCE"; score=10
        else:
            cls="CROSS_ROUTE_OR_CONTEXT_DIVERGENCE"; score=50
        if contamination: score+=15
        if effective: score+=20

        record={"priority":score,"classification":cls,"type_hex":g["type_hex"],
            "canonical_path":g["canonical_path"],"provider_count":g["provider_count"],
            "payload_variants":g["payload_variants"],"active_payload_variants":active_variants,
            "same_family_conflicts":same_family,"same_route_conflicts":same_route,
            "route_summary":route_summary,
            "consensus_outlier_providers":consensus_outliers,
            "contaminating_providers":sorted(contamination),"observed_effective_provider":effective}
        if args.verbose:
            record["providers"]=ps
        groups.append(record)
    conn.close()
    if args.actionable:
        groups=[g for g in groups if g["classification"]!="EXPECTED_ENG_JPN_DIVERGENCE" or g["contaminating_providers"]]
    groups.sort(key=lambda g:(-g["priority"],g["canonical_path"],g["type_hex"]))
    total=len(groups)
    if args.limit is not None: groups=groups[:args.limit]
    print(json.dumps({"count":len(groups),"total_matching":total,"groups":groups},indent=2)); return 0
