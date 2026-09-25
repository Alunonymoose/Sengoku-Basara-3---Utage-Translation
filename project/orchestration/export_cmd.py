from __future__ import annotations
import csv
import json
from collections import defaultdict
from pathlib import Path

from core import atomic_json, find_repo_root, load_ownership_module
from db import connect_db
from resolver import resolve_snapshot


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def export_ownership_command(args)->int:
    db=resolve_snapshot(args.snapshot)
    repo=Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
    own=load_ownership_module(repo)
    conn=connect_db(db)
    meta={r["key"]:json.loads(r["value"]) for r in conn.execute("SELECT key,value FROM metadata")}
    rows=[]
    for r in conn.execute("""SELECT f.path arc,r.member_index AS 'index',r.internal_path physical_path,
        r.canonical_path exact_path,r.type_hash,r.type_hex,r.stored_sha256,r.raw_sha256,
        r.compressed_size stored_size,r.actual_raw_size expanded_size,r.flags,r.data_offset,
        r.codec,r.warning,aro.runtime_rank
        FROM resources r JOIN arcs a ON a.id=r.arc_id JOIN files f ON f.id=a.file_id
        LEFT JOIN arc_runtime_order aro ON aro.arc_id=a.id
        ORDER BY f.path,r.member_index"""):
        d=dict(r)
        raw=d["exact_path"].encode("latin1",errors="replace")
        d["locale_equiv_path"]=own.display_bytes(own.locale_equiv(raw))
        d["type_name"]=own.KNOWN_TYPES.get(d["type_hash"],"")
        d["expanded_sha256"]=d.pop("raw_sha256")
        d["decode_method"]="zlib_validated" if d.pop("codec")=="zlib" else "raw_size_match"
        d["bounds_ok"]=True
        rows.append(d)

    by_exact=defaultdict(list); by_locale=defaultdict(list)
    for d in rows:
        by_exact[(d["type_hash"],d["exact_path"])].append(d)
        by_locale[(d["type_hash"],d["locale_equiv_path"])].append(d)

    groups=[]
    for (th,path),ps in by_exact.items():
        if len(ps)<2: continue
        variants={p["expanded_sha256"] for p in ps}
        cls="SAFE_IDENTICAL_EXPANDED" if len(variants)==1 else "DIVERGENT"
        ranked=[p for p in ps if p["runtime_rank"] is not None]
        ranked.sort(key=lambda p:p["runtime_rank"] if p["runtime_rank"] is not None else 10**12)
        effective=ranked[0]["arc"] if ranked else None
        risk=("DIVERGENT_EFFECTIVE_PROVIDER_KNOWN" if cls=="DIVERGENT" and effective else
              "DIVERGENT_ORDER_UNKNOWN" if cls=="DIVERGENT" else "SAFE_IDENTICAL")
        groups.append({"type_hash":th,"type_hex":f"0x{th:08X}","type_name":own.KNOWN_TYPES.get(th,""),
                       "exact_path":path,"provider_count":len(ps),"classification":cls,"risk":risk,
                       "effective_provider":effective,"effective_order_index":ranked[0]["runtime_rank"] if ranked else None,
                       "providers":ps})
    groups.sort(key=lambda g:(0 if g["classification"]=="DIVERGENT" else 1,g["type_hex"],g["exact_path"]))

    locale_groups=[]
    for (th,path),ps in by_locale.items():
        ids={(p["type_hash"],p["exact_path"]) for p in ps}
        if len(ids)>1:
            locale_groups.append({"type_hash":th,"type_hex":f"0x{th:08X}","type_name":own.KNOWN_TYPES.get(th,""),
                                  "locale_equiv_path":path,"provider_count":len(ps),"exact_identity_count":len(ids),
                                  "providers":ps})

    parse_errors=[dict(r) for r in conn.execute("""SELECT f.path arc,a.error FROM arcs a JOIN files f ON f.id=a.file_id WHERE a.parse_status!='OK' ORDER BY f.path""")]
    conn.close()
    summary={"format":"BASARA_FOUNDRY_RESOURCE_OWNERSHIP_V1","root":meta.get("scan_root"),
             "snapshot_id":meta.get("snapshot_id"),"arc_count":len({r["arc"] for r in rows}),
             "resource_count":len(rows),"exact_duplicate_class_count":len(groups),
             "safe_identical_expanded":sum(g["classification"]=="SAFE_IDENTICAL_EXPANDED" for g in groups),
             "safe_identical_raw":0,"divergent_exact_duplicate_classes":sum(g["classification"]=="DIVERGENT" for g in groups),
             "unresolved_compression_classes":0,"locale_equivalence_class_count":len(locale_groups),
             "load_order_source":meta.get("rpcs3_log"),"load_order_event_count":meta.get("rpcs3_load_events",0),
             "parse_error_count":len(parse_errors),
             "precedence_model":"first successful payload population claim wins among co-resident exact typed/path duplicates",
             "warning":"effective_provider is emitted only from bound runtime-order evidence; static filesystem order is never runtime precedence"}
    report={"summary":summary,"parse_errors":parse_errors,"exact_duplicate_classes":groups,"locale_equivalence_classes":locale_groups}
    out=Path(args.out).resolve(); out.mkdir(parents=True,exist_ok=True)
    atomic_json(out/"resource_ownership.json",report)
    fields=["arc","index","physical_path","exact_path","locale_equiv_path","type_hex","type_name","stored_size","expanded_size","flags","data_offset","stored_sha256","expanded_sha256","decode_method","bounds_ok"]
    _write_csv(out/"resources.csv",rows,fields)
    _write_csv(out/"duplicate_classes.csv",[
        {**{k:g.get(k) for k in ["type_hex","type_name","exact_path","provider_count","classification","risk","effective_provider","effective_order_index"]},
         "providers":" | ".join(p["arc"] for p in g["providers"])} for g in groups],
        ["type_hex","type_name","exact_path","provider_count","classification","risk","effective_provider","effective_order_index","providers"])
    print(json.dumps({"snapshot_id":meta.get("snapshot_id"),"resource_count":len(rows),"duplicate_groups":len(groups),"divergent_groups":sum(g["classification"]=="DIVERGENT" for g in groups),"out":str(out)},indent=2))
    return 0
