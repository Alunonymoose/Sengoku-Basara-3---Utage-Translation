
from pathlib import Path
import csv,json,sys,importlib.util
from PIL import Image,ImageDraw,ImageFont

OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
ROOT=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
rows=list(csv.DictReader(open(OUT/"LAYOUT_REFERENCED_TEXTURE_AUDIT.csv",encoding="utf-8-sig")))
cand=[r for r in rows if r["jpn_state"]!="EXACT" and r["sh_state"]!="EXACT"]

# Dedup by current raw hash; A-Z representative.
groups={}
for r in cand:
    h=r["eng_sha256"]
    g=groups.setdefault(h,{"owners":[]})
    g["owners"].append(r)
unique=[]
for h,g in groups.items():
    owners=sorted(g["owners"],key=lambda r:(r["arc_path"].lower(),int(r["member_index"])))
    rep=owners[0]
    unique.append({"raw_sha256":h,"rep":rep,"owners":owners})
unique.sort(key=lambda g:(g["rep"]["arc_path"].lower(),int(g["rep"]["member_index"])))

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"))
xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

pngdir=OUT/"layout_custom_png";sheetdir=OUT/"layout_custom_sheets"
pngdir.mkdir(exist_ok=True);sheetdir.mkdir(exist_ok=True)
cache={}
records=[]
for i,g in enumerate(unique,1):
    r=g["rep"];p=ROOT/Path(r["arc_path"])
    key=str(p)
    if key not in cache:cache[key]=parse_arc(p)
    a=cache[key];e=a.entries[int(r["member_index"])]
    try:
        im=Image.fromarray(xet.decode_display(unpack_entry(e)),"RGBA")
    except Exception:
        continue
    uid=f"Q{i:03d}"
    fp=pngdir/f"{uid}_FULL.png";im.save(fp)
    consumers=json.loads(r["consumers"])
    # choose largest valid source crop among all equivalent owner records/consumers
    valid=[]
    for owner in g["owners"]:
        try: cons=json.loads(owner["consumers"])
        except: cons=[]
        for c in cons:
            x0,y0,x1,y1=map(int,c["src"])
            if 0<=x0<x1<=im.width and 0<=y0<y1<=im.height:
                valid.append(((x1-x0)*(y1-y0),(x0,y0,x1,y1),c,owner["arc_path"]))
    valid.sort(key=lambda x:x[0],reverse=True)
    cp=None;crop_rect=None;crop_consumer=None
    if valid:
        _,crop_rect,crop_consumer,crop_owner=valid[0]
        cp=pngdir/f"{uid}_CROP.png";im.crop(crop_rect).save(cp)
    records.append({
        "uid":uid,"arc_path":r["arc_path"],"member_index":int(r["member_index"]),
        "texture_name":r["texture_name"],"raw_sha256":g["raw_sha256"],
        "owner_records":len(g["owners"]),
        "jpn_state":r["jpn_state"],"sh_state":r["sh_state"],
        "default_visible_count":sum(int(o["default_visible_count"]) for o in g["owners"]),
        "animated_consumer_count":sum(int(o["animated_consumer_count"]) for o in g["owners"]),
        "full_png":str(fp),"crop_png":str(cp) if cp else None,
        "crop_rect":crop_rect,"crop_consumer":crop_consumer
    })

(OUT/"LAYOUT_CUSTOM_REVIEW.json").write_text(json.dumps(records,indent=2),encoding="utf-8")

# 3x3 review sheets, A-Z.
COLS=3;ROWS=3;CW=360;PH=210;LH=60;CELLH=PH+LH
font=ImageFont.load_default();manifest=[]
for start in range(0,len(records),9):
    batch=records[start:start+9]
    sh=Image.new("RGB",(COLS*CW,ROWS*CELLH),(38,38,38));d=ImageDraw.Draw(sh)
    for j,r in enumerate(batch):
        rr=j//COLS;cc=j%COLS;x=cc*CW;y=rr*CELLH
        full=Image.open(r["full_png"]).convert("RGBA")
        crop=Image.open(r["crop_png"]).convert("RGBA") if r["crop_png"] else full
        for pane,im,label in [(0,full,"FULL"),(1,crop,"LIVE CROP")]:
            pw=CW//2;scale=min((pw-8)/im.width,(PH-8)/im.height)
            rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
            bg=Image.new("RGBA",(pw,PH),(96,96,96,255));bg.alpha_composite(rim,((pw-rim.width)//2,(PH-rim.height)//2))
            sh.paste(bg.convert("RGB"),(x+pane*pw,y));d.text((x+pane*pw+4,y+4),label,fill=(255,220,120),font=font)
        d.rectangle((x,y+PH,x+CW,y+CELLH),fill=(16,16,16))
        d.text((x+4,y+PH+3),f'{r["uid"]} {r["arc_path"]}:{r["member_index"]}',fill="white",font=font)
        d.text((x+4,y+PH+17),r["texture_name"].split("\\")[-1][:50],fill=(210,210,210),font=font)
        d.text((x+4,y+PH+31),f'owners={r["owner_records"]} vis={r["default_visible_count"]} anim={r["animated_consumer_count"]}',fill=(170,170,170),font=font)
        d.text((x+4,y+PH+45),f'{r["jpn_state"]}/{r["sh_state"]} crop={r["crop_rect"]}',fill=(145,145,145),font=font)
    p=sheetdir/f"CUSTOM_{start//9+1:02d}.jpg";sh.save(p,quality=92)
    manifest.append({"sheet":p.name,"uids":[r["uid"] for r in batch]})
(OUT/"LAYOUT_CUSTOM_REVIEW_MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps({"placements":len(cand),"unique_current_hashes":len(records),"sheets":len(manifest)},indent=2))
