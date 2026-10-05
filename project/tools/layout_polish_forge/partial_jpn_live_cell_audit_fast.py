
from pathlib import Path
import csv,json,sys,importlib.util,hashlib,collections
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
rows=list(csv.DictReader(open(OUT/"LAYOUT_REFERENCED_TEXTURE_AUDIT.csv",encoding="utf-8-sig")))

# Only textures whose whole ENG resource differs from JPN.
rows=[r for r in rows if r["jpn_state"]=="DIFF"]

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"))
xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

cache={}
decode_cache={}
def pa(p):
 k=str(p)
 if k not in cache: cache[k]=parse_arc(p)
 return cache[k]
def find(a,name):
 low=name.lower(); hits=[e for e in a.entries if e.name.lower()==low]
 return hits[0] if len(hits)==1 else None
def get_pair(rel,name):
 k=(rel,name.lower())
 if k in decode_cache:return decode_cache[k]
 ep=ENG/rel;jp=JPN/rel
 if not jp.exists():decode_cache[k]=(None,None);return None,None
 try:
  ea=pa(ep);ja=pa(jp);ee=find(ea,name);je=find(ja,name)
  if not ee or not je: raise RuntimeError("member miss")
  er=xet.decode_display(unpack_entry(ee));jr=xet.decode_display(unpack_entry(je))
  if er.shape!=jr.shape: raise RuntimeError("shape mismatch")
  decode_cache[k]=(er,jr);return er,jr
 except:
  decode_cache[k]=(None,None);return None,None

findings=[]
seen=set()
for r in rows:
 rel=r["arc_path"].replace("\\","/")
 name=r["texture_name"]
 er,jr=get_pair(rel,name)
 if er is None:continue
 H,W=er.shape[:2]
 try:cons=json.loads(r["consumers"])
 except:continue
 for c in cons:
  rect=tuple(map(int,c["src"]))
  key=(rel,name.lower(),rect,c["layout"],int(c["node_index"]))
  if key in seen:continue
  seen.add(key)
  x0,y0,x1,y1=rect
  if not (0<=x0<x1<=W and 0<=y0<y1<=H):continue
  ec=er[y0:y1,x0:x1];jc=jr[y0:y1,x0:x1]
  alpha=jc[...,3]>16
  visible=float(alpha.mean())
  if visible<0.005:continue
  diff=np.abs(ec.astype(np.int16)-jc.astype(np.int16))
  exact=bool(np.array_equal(ec,jc))
  same=float((diff<=2).all(axis=2).mean())
  mae=float(diff.mean())
  if not exact and not (same>=0.998 and mae<=0.10):continue

  area=(x1-x0)*(y1-y0)
  score=100
  if bool(c.get("default_display")):score+=25
  if area<=140*90:score+=20
  if (x1-x0)<=320 and (y1-y0)<=180:score+=10
  node=str(c.get("node_name",""))
  if node.lower() in ("text","title","name","page","system","details","up04","win","lose","yes","no","lv","kakutoku","senmei"):score+=20
  findings.append({
   "score":score,"arc_path":rel,"member_index":int(r["member_index"]),"texture_name":name,
   "layout":c["layout"],"node_index":int(c["node_index"]),"node_name":node,
   "default_visible":bool(c.get("default_display")),"animated":bool(c.get("animated")),
   "rect":list(rect),"crop_size":[x1-x0,y1-y0],
   "visible_coverage":round(visible,4),"exact":exact,"same_px_ratio":round(same,5),"mae":round(mae,5)
  })

# Dedup resource+rect; keep strongest consumer metadata.
best={}
for f in findings:
 k=(f["arc_path"],f["member_index"],tuple(f["rect"]))
 if k not in best or f["score"]>best[k]["score"]:best[k]=f
findings=sorted(best.values(),key=lambda x:(-x["score"],x["arc_path"].lower(),x["member_index"],x["rect"]))
for i,f in enumerate(findings,1):f["uid"]=f"J{i:03d}"

(OUT/"PARTIAL_JPN_LIVE_CELL_AUDIT_FAST.json").write_text(json.dumps(findings,indent=2),encoding="utf-8")

imgdir=OUT/"partial_jpn_cell_fast_png";sheetdir=OUT/"partial_jpn_cell_fast_sheets"
imgdir.mkdir(exist_ok=True);sheetdir.mkdir(exist_ok=True)
review=findings[:54]
for f in review:
 er,jr=get_pair(f["arc_path"],f["texture_name"])
 x0,y0,x1,y1=f["rect"]
 Image.fromarray(er[y0:y1,x0:x1],"RGBA").save(imgdir/f'{f["uid"]}_ENG.png')
 Image.fromarray(jr[y0:y1,x0:x1],"RGBA").save(imgdir/f'{f["uid"]}_JPN.png')

CW=360;PH=170;LH=74;font=ImageFont.load_default()
for start in range(0,len(review),9):
 batch=review[start:start+9]
 sheet=Image.new("RGB",(CW*3,(PH+LH)*3),(40,40,40));d=ImageDraw.Draw(sheet)
 for j,f in enumerate(batch):
  rr=j//3;cc=j%3;x=cc*CW;y=rr*(PH+LH)
  im=Image.open(imgdir/f'{f["uid"]}_ENG.png').convert("RGBA")
  scale=min((CW-8)/im.width,(PH-8)/im.height)
  rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.NEAREST)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  sheet.paste(bg.convert("RGB"),(x,y))
  d.rectangle((x,y+PH,x+CW,y+PH+LH),fill=(15,15,15))
  d.text((x+4,y+PH+3),f'{f["uid"]} {f["arc_path"]}:{f["member_index"]} score={f["score"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),f["texture_name"].split("\\")[-1][:48],fill=(210,210,210),font=font)
  d.text((x+4,y+PH+31),f'{f["node_name"]} rect={f["rect"]}',fill=(180,180,180),font=font)
  d.text((x+4,y+PH+45),f'cell still JPN-identical; vis={f["visible_coverage"]}',fill=(150,150,150),font=font)
 sheet.save(sheetdir/f"PARTIAL_JPN_{start//9+1:02d}.jpg",quality=94)

print(json.dumps({
 "whole_texture_translated_rows":len(rows),
 "partial_jpn_cells":len(findings),
 "review_sheets":(len(review)+8)//9,
 "top":findings[:50]
},indent=2))
