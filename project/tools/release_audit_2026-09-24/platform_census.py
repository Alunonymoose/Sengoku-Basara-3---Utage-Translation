#!/usr/bin/env python3
"""Read-only PS3 platform / XMB / trophy / loose-resource census for BASARA Foundry."""
from __future__ import annotations
import argparse, csv, hashlib, json, struct, sys
from pathlib import Path

SCHEMA="BASARA_FOUNDRY_PLATFORM_CENSUS_V1"

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def has_japanese(s:str)->bool:
    return any(
        "\u3040"<=c<="\u30ff" or "\u3400"<=c<="\u4dbf" or "\u4e00"<=c<="\u9fff"
        for c in s
    )

def parse_sfo(raw:bytes)->dict:
    if len(raw)<20 or raw[:4]!=b"\x00PSF": raise ValueError("not PARAM.SFO/PSF")
    magic,version,key_off,data_off,count=struct.unpack_from("<4sIIII",raw,0)
    table_end=20+count*16
    if table_end>len(raw) or key_off>len(raw) or data_off>len(raw):
        raise ValueError("SFO table outside file")
    entries=[]
    for i in range(count):
        o=20+i*16
        ko,fmt,n,maxn,do=struct.unpack_from("<HHIII",raw,o)
        ks=key_off+ko
        if ks>=len(raw): raise ValueError(f"key offset outside file at entry {i}")
        ke=raw.find(b"\0",ks)
        if ke<0: raise ValueError(f"unterminated SFO key at entry {i}")
        key=raw[ks:ke].decode("utf-8","replace")
        ds=data_off+do
        if ds+n>len(raw): raise ValueError(f"data outside file at entry {i}")
        b=raw[ds:ds+n]
        if fmt==0x0204:
            value=b.split(b"\0",1)[0].decode("utf-8","replace")
            kind="UTF8"
        elif fmt==0x0404 and len(b)>=4:
            value=struct.unpack_from("<I",b,0)[0]
            kind="UINT32"
        else:
            value=b.hex()
            kind=f"BINARY_0x{fmt:04X}"
        entries.append({"key":key,"format":f"0x{fmt:04X}","kind":kind,"value":value,"max_len":maxn})
    return {"version":f"0x{version:08X}","entries":entries}

def classify(p:Path,root:Path)->str|None:
    rel=p.relative_to(root).as_posix()
    up=rel.upper()
    name=p.name.upper()
    if name=="PARAM.SFO": return "PARAM_SFO"
    if name in {"ICON0.PNG","PIC0.PNG","PIC1.PNG","ICON1.PMF","SND0.AT3"}: return "XMB_SURFACE"
    if "/TROPDIR/" in "/"+up or up.startswith("TROPDIR/"): return "TROPHY"
    if "/LICDIR/" in "/"+up or up.startswith("LICDIR/"): return "LICENSE"
    if "SYSTEM/FONT" in up: return "SYSTEM_FONT"
    if any(x in up for x in ("/STARTUP","/SAVE","/SYSTEM/")) and p.suffix.lower()!=".arc": return "STARTUP_SAVE_SYSTEM_LOOSE"
    if p.suffix.lower() in {".xet",".tex",".gmd",".msg",".lsp",".psl"}: return "LOOSE_GAME_RESOURCE"
    return None

def decode_text_preview(raw:bytes,suffix:str)->str|None:
    if suffix.lower() not in {".txt",".xml",".ini",".cfg",".json",".md",".sfm"}: return None
    for enc in ("utf-8-sig","utf-16"):
        try:
            s=raw.decode(enc)
            if "\x00" not in s[:200]:
                return s[:20000]
        except Exception: pass
    return None

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("root",type=Path); ap.add_argument("--out",type=Path,required=True)
    ns=ap.parse_args(); root=ns.root.resolve(); out=ns.out.resolve()
    if not root.is_dir(): return 3
    out.mkdir(parents=True,exist_ok=True)
    rows=[]; sfo_entries=[]; errors=[]
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        cls=classify(p,root)
        if cls is None: continue
        try:
            raw=p.read_bytes()
            text=decode_text_preview(raw,p.suffix)
            row={
                "relative_path":p.relative_to(root).as_posix(),
                "sha256":hashlib.sha256(raw).hexdigest(),
                "size":len(raw),
                "surface_class":cls,
                "parse_status":"HASHED",
                "text_preview":text,
                "japanese_script_signal":has_japanese(text) if text else False,
                "review_state":"NEEDS_REVIEW",
            }
            if cls=="PARAM_SFO":
                parsed=parse_sfo(raw)
                row["parse_status"]="PARSED_PARAM_SFO"
                vals=[]
                for e in parsed["entries"]:
                    ee=dict(e); ee["relative_path"]=row["relative_path"]; sfo_entries.append(ee)
                    if e["kind"]=="UTF8":
                        vals.append(f"{e['key']}={e['value']}")
                        if has_japanese(str(e["value"])): row["japanese_script_signal"]=True
                row["text_preview"]="\n".join(vals)
            elif cls=="SYSTEM_FONT":
                row["review_state"]="STRUCTURAL_REFERENCE"
            elif cls=="XMB_SURFACE":
                row["review_state"]="VISUAL_REVIEW_REQUIRED"
            elif cls=="TROPHY":
                row["review_state"]="TROPHY_SEMANTIC_REVIEW_REQUIRED"
            rows.append(row)
        except Exception as e:
            errors.append({"path":p.relative_to(root).as_posix(),"error":repr(e)})
    summary={
        "schema":SCHEMA,
        "record_count":len(rows),
        "param_sfo_entries":len(sfo_entries),
        "japanese_script_signals":sum(r["japanese_script_signal"] for r in rows),
        "visual_review_required":sum(r["review_state"]=="VISUAL_REVIEW_REQUIRED" for r in rows),
        "trophy_review_required":sum(r["review_state"]=="TROPHY_SEMANTIC_REVIEW_REQUIRED" for r in rows),
        "errors":len(errors),
        "release_pass":False,
        "release_pass_reason":"Platform/loose surfaces require semantic and visual disposition; this census only makes them complete and visible."
    }
    (out/"LOOSE_UI_AND_METADATA_CENSUS.json").write_text(json.dumps({"summary":summary,"records":rows,"param_sfo":sfo_entries,"errors":errors},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    fields=["relative_path","sha256","size","surface_class","parse_status","japanese_script_signal","review_state","text_preview"]
    with (out/"LOOSE_UI_AND_METADATA_CENSUS.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary,indent=2))
    return 1 if errors else 0

if __name__=="__main__": raise SystemExit(main())
