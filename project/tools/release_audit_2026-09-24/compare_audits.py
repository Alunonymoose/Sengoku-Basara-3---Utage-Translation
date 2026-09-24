#!/usr/bin/env python3
"""Compare two BASARA Foundry release-audit directories by stable identities."""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA="BASARA_FOUNDRY_AUDIT_DIFF_V1"

def load(path:Path,name:str,default:Any):
    p=path/name
    if not p.is_file(): return default
    return json.loads(p.read_text(encoding="utf-8"))

def diff_map(old:dict,new:dict):
    oldk=set(old); newk=set(new)
    added=sorted(newk-oldk); removed=sorted(oldk-newk)
    changed=sorted(k for k in oldk&newk if old[k]!=new[k])
    unchanged=len(oldk&newk)-len(changed)
    return {"added":added,"removed":removed,"changed":changed,"unchanged_count":unchanged}

def file_map(d:Path):
    j=load(d,"FILE_TREE_HASHES.json",{})
    return {r["relative_path"]:(r.get("size"),r.get("sha256"),r.get("class"),r.get("status"))
            for r in j.get("files",[])}

def member_map(d:Path):
    j=load(d,"ARC_MEMBERS.json",{})
    out={}
    for r in j.get("members",[]):
        key=f"{r.get('arc_relative_path')}|{r.get('member_index')}|{r.get('type_hash')}|{r.get('internal_path')}"
        out[key]=(r.get("stored_sha256"),r.get("expanded_sha256"),r.get("flags"),r.get("codec"),r.get("warning"))
    return out

def texture_map(d:Path):
    j=load(d,"TEXTURE_CENSUS.json",{})
    out={}
    for r in j.get("textures",[]):
        key=f"{r.get('arc_relative_path')}|{r.get('member_index')}|{r.get('internal_path')}"
        out[key]=(r.get("raw_sha256"),r.get("decoded_rgba_sha256"),r.get("width"),r.get("height"),
                  r.get("mip_count"),r.get("format_id"),r.get("decoder_status"),r.get("semantic_classification"))
    return out

def message_map(d:Path):
    j=load(d,"MESSAGE_CENSUS.json",{})
    out={}
    for r in j.get("records",[]):
        key=f"{r.get('arc_relative_path')}|{r.get('resource_name')}|{r.get('record_index')}"
        out[key]=(r.get("text"),r.get("stray_glyph_count"),r.get("visual_line_count"),
                  r.get("line_lengths_chars"),r.get("heuristic_over_41_chars"),r.get("parse_status"))
    return out

def generic_records(d:Path,name:str):
    j=load(d,name,{})
    recs=j.get("records",[])
    return {r.get("relative_path"):(r.get("sha256"),r.get("review_state"),r.get("release_state"),
                                    r.get("subtitle_requirement"),r.get("runtime_status"),
                                    r.get("japanese_script_signal"))
            for r in recs if r.get("relative_path")}

def unresolved_counts(d:Path):
    j=load(d,"UNRESOLVED.json",{})
    return dict(Counter((x.get("category") or "UNKNOWN") for x in j.get("items",[])))

def donor_summary(d:Path):
    j=load(d,"DONOR_CANDIDATES.json",{})
    recs=j.get("records",[])
    decisions=Counter((r.get("decision") or "UNKNOWN") for r in recs)
    providers=Counter((r.get("provider_status") or "NONE") for r in recs)
    return {"records":len(recs),"by_decision":dict(decisions),"by_provider_status":dict(providers)}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("prior",type=Path); ap.add_argument("current",type=Path)
    ap.add_argument("--out",type=Path,required=True)
    ns=ap.parse_args(); old=ns.prior.resolve(); new=ns.current.resolve(); out=ns.out.resolve()
    if not old.is_dir() or not new.is_dir(): return 3
    out.mkdir(parents=True,exist_ok=True)

    sections={
        "files":diff_map(file_map(old),file_map(new)),
        "arc_members":diff_map(member_map(old),member_map(new)),
        "textures":diff_map(texture_map(old),texture_map(new)),
        "messages":diff_map(message_map(old),message_map(new)),
        "media":diff_map(generic_records(old,"MEDIA_CENSUS.json"),generic_records(new,"MEDIA_CENSUS.json")),
        "platform":diff_map(generic_records(old,"LOOSE_UI_AND_METADATA_CENSUS.json"),
                            generic_records(new,"LOOSE_UI_AND_METADATA_CENSUS.json")),
    }
    oldmeta=load(old,"00_RUN_METADATA.json",{})
    newmeta=load(new,"00_RUN_METADATA.json",{})
    payload={
        "schema":SCHEMA,
        "prior":{"path":str(old),"live_tree_sha256":oldmeta.get("live_tree_sha256"),"candidate":oldmeta.get("status")},
        "current":{"path":str(new),"live_tree_sha256":newmeta.get("live_tree_sha256"),"candidate":newmeta.get("status")},
        "sections":sections,
        "unresolved":{"prior":unresolved_counts(old),"current":unresolved_counts(new)},
        "donor":{"prior":donor_summary(old),"current":donor_summary(new)},
    }
    (out/"AUDIT_DIFF.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    lines=["# BASARA Foundry Audit Diff","",
           f"- Prior tree: `{payload['prior']['live_tree_sha256']}`",
           f"- Current tree: `{payload['current']['live_tree_sha256']}`",""]
    for name,d in sections.items():
        lines += [f"## {name.replace('_',' ').title()}",
                  f"- Added: {len(d['added'])}",
                  f"- Removed: {len(d['removed'])}",
                  f"- Changed: {len(d['changed'])}",
                  f"- Unchanged: {d['unchanged_count']}",""]
        for label in ("added","removed","changed"):
            if d[label]:
                lines.append(f"### {label.title()}")
                lines += [f"- `{x}`" for x in d[label][:200]]
                if len(d[label])>200: lines.append(f"- … {len(d[label])-200} more")
                lines.append("")
    lines += ["## Unresolved categories","",
              f"- Prior: `{json.dumps(payload['unresolved']['prior'],sort_keys=True)}`",
              f"- Current: `{json.dumps(payload['unresolved']['current'],sort_keys=True)}`","",
              "## Donor summary","",
              f"- Prior: `{json.dumps(payload['donor']['prior'],sort_keys=True)}`",
              f"- Current: `{json.dumps(payload['donor']['current'],sort_keys=True)}`",""]
    (out/"AUDIT_DIFF.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({
        "prior_tree":payload["prior"]["live_tree_sha256"],
        "current_tree":payload["current"]["live_tree_sha256"],
        "changed_files":len(sections["files"]["changed"]),
        "changed_arc_members":len(sections["arc_members"]["changed"]),
        "changed_textures":len(sections["textures"]["changed"]),
        "changed_messages":len(sections["messages"]["changed"]),
        "out":str(out)
    },indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
