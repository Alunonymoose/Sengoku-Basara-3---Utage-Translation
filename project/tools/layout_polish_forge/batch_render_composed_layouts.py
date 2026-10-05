
from pathlib import Path
import sys, json, io, contextlib, csv, re
from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageFont

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa\composed_layouts")
PNG=OUT/"png"
SHEETS=OUT/"sheets"
PNG.mkdir(parents=True,exist_ok=True);SHEETS.mkdir(parents=True,exist_ok=True)

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\utage_harness")
import utage_harness as h

# Use psl-sweep's same authoritative discovery rule, directly against CURRENT LIVE.
layouts=[]
for path in sorted(ENG.rglob("*.arc"),key=lambda p:str(p.relative_to(ENG)).lower()):
    try:
        arc=h.core.parse_arc(path)
    except Exception:
        continue
    for entry in arc.entries:
        if entry.type_hash != 0x60DD1B16 and not entry.name.lower().endswith(".lsp"):
            continue
        try:
            raw=h.core.unpack_entry(entry)
            if not h.lsp.is_layout(raw): continue
            lay=h.lsp.parse_layout(raw,entry.name)
        except Exception:
            continue
        layouts.append({
            "arc":str(path),
            "rel_arc":str(path.relative_to(ENG)).replace("\\","/"),
            "member":entry.name,
            "member_index":entry.index,
            "nodes":len(lay.nodes),
            "animations":len(lay.animations)
        })

reports=[]
for i,item in enumerate(layouts,1):
    out=PNG/f"L{i:03d}.png"
    args=SimpleNamespace(
        arc=item["arc"],out=str(out),layout=item["member"],match=None,node=None,
        atlas_scale=2.0,logical_size=(640,480),output_size=(640,480),
        background=(88,88,88,255),animation_root=None,frame=0,respect_alpha=True,
        include_static=False,rrc=None,rrc_surface="dominant"
    )
    buf=io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            h.cmd_render_layout(args)
        report=json.loads(buf.getvalue())
        reports.append({
            **item,"uid":f"L{i:03d}","status":"OK",
            "rendered_count":len(report.get("rendered",[])),
            "skipped_count":len(report.get("skipped",[])),
            "skipped":report.get("skipped",[]),"png":str(out)
        })
    except Exception as ex:
        reports.append({**item,"uid":f"L{i:03d}","status":"ERROR","error":repr(ex),"png":str(out)})

(OUT/"LAYOUT_RENDER_REPORT.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")
with (OUT/"LAYOUT_RENDER_REPORT.csv").open("w",newline="",encoding="utf-8-sig") as f:
    fields=["uid","rel_arc","member_index","member","nodes","animations","status","rendered_count","skipped_count","png"]
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in reports:w.writerow({k:r.get(k,"") for k in fields})

# Contact sheets: 3x3, bigger cells so text remains readable.
ok=[r for r in reports if r["status"]=="OK" and Path(r["png"]).exists()]
COLS=3;ROWS=3;PW=320;PH=240;LH=44;CELLH=PH+LH
font=ImageFont.load_default()
manifest=[]
for start in range(0,len(ok),COLS*ROWS):
    batch=ok[start:start+COLS*ROWS]
    sh=Image.new("RGB",(COLS*PW,ROWS*CELLH),(35,35,35));d=ImageDraw.Draw(sh)
    for j,r in enumerate(batch):
        im=Image.open(r["png"]).convert("RGB").resize((PW,PH),Image.Resampling.LANCZOS)
        rr=j//COLS;cc=j%COLS;x=cc*PW;y=rr*CELLH
        sh.paste(im,(x,y))
        d.rectangle((x,y+PH,x+PW,y+CELLH),fill=(12,12,12))
        d.text((x+4,y+PH+4),f'{r["uid"]} {r["rel_arc"]}',fill="white",font=font)
        label=r["member"].split("\\")[-1]
        d.text((x+4,y+PH+18),f'{label}  nodes={r["nodes"]} anim={r["animations"]}',fill=(205,205,205),font=font)
        d.text((x+4,y+PH+31),f'rendered={r["rendered_count"]} skipped={r["skipped_count"]}',fill=(165,165,165),font=font)
    p=SHEETS/f"COMPOSED_{start//9+1:02d}.jpg";sh.save(p,quality=92)
    manifest.append({"sheet":p.name,"uids":[r["uid"] for r in batch]})
(OUT/"SHEET_MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps({
    "layouts":len(layouts),
    "ok":len(ok),
    "errors":sum(r["status"]!="OK" for r in reports),
    "sheets":len(manifest),
    "error_rows":[r for r in reports if r["status"]!="OK"]
},indent=2))
