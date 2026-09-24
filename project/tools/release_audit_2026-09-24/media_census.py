#!/usr/bin/env python3
"""Read-only BASARA Foundry PAM/media census."""
from __future__ import annotations
import argparse, csv, hashlib, json, sys
from pathlib import Path

SCHEMA="BASARA_FOUNDRY_MEDIA_CENSUS_V1"

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def family_hint(name:str)->str:
    n=name.lower()
    for p,label in (("op","OPENING_HINT"),("ed","ENDING_HINT"),("adv","ADV_HINT"),("staff","STAFF_HINT")):
        if n.startswith(p): return label
    return "UNKNOWN"

def inspect_pam(p:Path,root:Path)->dict:
    with p.open("rb") as f: head=f.read(0x800)
    ascii_head=head[:16].decode("ascii","replace")
    magic=head[:8].rstrip(b"\0").decode("ascii","replace")
    return {
        "relative_path":p.relative_to(root).as_posix(),
        "sha256":sha256_file(p),
        "size":p.stat().st_size,
        "container_magic":magic,
        "header_first16_ascii":ascii_head,
        "header_first16_hex":head[:16].hex(),
        "pamf_family":magic.startswith("PAMF"),
        "known_pilot_match":p.name.lower()=="op029_00.pam",
        "name_family_hint":family_hint(p.stem),
        "duration":None,
        "video_codec":None,
        "resolution":None,
        "framerate":None,
        "audio_codec":None,
        "audio_channels":None,
        "audio_rate":None,
        "mapped_context":None,
        "shared_sh_match":None,
        "subtitle_requirement":"UNKNOWN",
        "subtitle_script_status":"UNKNOWN",
        "mux_status":"SOURCE_ONLY",
        "runtime_status":"NOT_TESTED",
        "final_output_hash":None,
        "release_state":"NEEDS_REVIEW",
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("root",type=Path)
    ap.add_argument("--out",type=Path,required=True)
    ns=ap.parse_args()
    root=ns.root.resolve(); out=ns.out.resolve()
    if not root.is_dir(): return 3
    out.mkdir(parents=True,exist_ok=True)
    rows=[]; errors=[]
    for p in sorted(root.rglob("*.pam")):
        try: rows.append(inspect_pam(p,root))
        except Exception as e: errors.append({"path":str(p),"error":repr(e)})
    summary={
        "schema":SCHEMA,
        "pam_count":len(rows),
        "pamf_magic_count":sum(r["pamf_family"] for r in rows),
        "unknown_subtitle_requirement":sum(r["subtitle_requirement"]=="UNKNOWN" for r in rows),
        "runtime_verified":sum(r["runtime_status"]=="RUNTIME_VERIFIED" for r in rows),
        "errors":len(errors),
        "release_pass":False,
        "release_pass_reason":"PAM identity-remux/hardsub pipeline and per-movie subtitle requirement remain runtime-open."
    }
    (out/"MEDIA_CENSUS.json").write_text(json.dumps({"summary":summary,"records":rows,"errors":errors},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    fields=list(rows[0].keys()) if rows else [
        "relative_path","sha256","size","container_magic","subtitle_requirement","runtime_status","release_state"
    ]
    with (out/"MEDIA_CENSUS.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary,indent=2))
    return 1 if errors else 0

if __name__=="__main__": raise SystemExit(main())
