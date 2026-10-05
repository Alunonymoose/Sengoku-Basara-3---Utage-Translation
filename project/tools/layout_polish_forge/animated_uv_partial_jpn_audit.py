
from pathlib import Path
import json,sys,importlib.util,hashlib,collections
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
layout_report=json.loads((OUT/"composed_layouts"/"LAYOUT_RENDER_REPORT.json").read_text(encoding="utf-8"))

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
from layout import parse_layout,is_layout
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"))
xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

arc_cache={}
pair_cache={}
def pa(p):
 k=str(p)
 if k not in arc_cache:arc_cache[k]=parse_arc(p)
 return arc_cache[k]
def find(a,name):
 low=name.lower();h=[e for e in a.entries if e.name.lower()==low]
 return h[0] if len(h)==1 else None
def pair(rel,name):
 k=(rel,name.lower())
 if k in pair_cache:return pair_cache[k]
 jp=JPN/rel
 if not jp.exists():pair_cache[k]=(None,None,None,None);return pair_cache[k]
 try:
  ea=pa(ENG/rel);ja=pa(jp);ee=find(ea,name);je=find(ja,name)
  if not ee or not je:raise RuntimeError()
  eraw=unpack_entry(ee);jraw=unpack_entry(je)
  if hashlib.sha256(eraw).digest()==hashlib.sha256(jraw).digest():
   pair_cache[k]=(None,None,ee,je);return pair_cache[k]
  er=xet.decode_display(eraw);jr=xet.decode_display(jraw)
  if er.shape!=jr.shape:raise RuntimeError()
  pair_cache[k]=(er,jr,ee,je);return pair_cache[k]
 except:
  pair_cache[k]=(None,None,None,None);return pair_cache[k]

findings=[]
seen=set()
for lr in layout_report:
 rel=lr["rel_arc"].replace("\\","/")
 p=ENG/rel
 try:
  a=pa(p);le=a.entries[int(lr["member_index"])]
  lay=parse_layout(unpack_entry(le),le.name)
 except:continue
 for an in lay.animations:
  tgt=lay.animation_target(an)
  if not tgt or tgt.node_type not in (2,3) or not tgt.texture:continue
  uvchs=[ch for ch in an.channels if ch.name=="uv_rect" and ch.keys]
  if not uvchs:continue
  er,jr,ee,je=pair(rel,tgt.texture)
  if er is None:continue
  H,W=er.shape[:2]
  for ch in uvchs:
   for key in ch.keys:
    vals=list(key.values)
    if len(vals)<4:continue
    x,y,w,h=vals[:4]
    rect=(int(round(x*2)),int(round(y*2)),int(round((x+w)*2)),int(round((y+h)*2)))
    x0,y0,x1,y1=rect
    if not(0<=x0<x1<=W and 0<=y0<y1<=H):continue
    sig=(rel,ee.index,rect)
    if sig in seen:continue
    seen.add(sig)
    ec=er[y0:y1,x0:x1];jc=jr[y0:y1,x0:x1]
    alpha=jc[...,3]>16
    vis=float(alpha.mean())
    if vis<0.005:continue
    diff=np.abs(ec.astype(np.int16)-jc.astype(np.int16))
    exact=bool(np.array_equal(ec,jc))
    same=float((diff<=2).all(axis=2).mean());mae=float(diff.mean())
    if not exact and not(same>=0.998 and mae<=0.10):continue
    area=(x1-x0)*(y1-y0);asp=(x1-x0)/max(1,y1-y0)
    score=100
    if area<=140*90:score+=20
    if asp>=1.4:score+=10
    names=(tgt.name+" "+an.name).lower()
    if any(t in names for t in ("text","title","name","page","up","save","load","rank","clear","result","mode","label","tassei","kotei","shuffle")):score+=30
    findings.append({
      "score":score,"arc_path":rel,"member_index":ee.index,"texture_name":ee.name,
      "layout":le.name,"animation_index":an.index,"animation_name":an.name,
      "target_node_index":tgt.index,"target_node_name":tgt.name,
      "key_time":key.time,"rect":list(rect),"crop_size":[x1-x0,y1-y0],
      "visible_coverage":round(vis,4),"exact":exact,"same_px_ratio":round(same,5),"mae":round(mae,5)
    })

findings.sort(key=lambda r:(-r["score"],r["arc_path"].lower(),r["member_index"],r["rect"]))
for i,r in enumerate(findings,1):r["uid"]=f"AJ{i:03d}"
(OUT/"ANIMATED_UV_PARTIAL_JPN_AUDIT.json").write_text(json.dumps(findings,indent=2),encoding="utf-8")

imgdir=OUT/"animated_uv_partial_png";sheetdir=OUT/"animated_uv_partial_sheets"
imgdir.mkdir(exist_ok=True);sheetdir.mkdir(exist_ok=True)
review=findings[:90]
for r in review:
 er,jr,ee,je=pair(r["arc_path"],r["texture_name"])
 x0,y0,x1,y1=r["rect"]
 Image.fromarray(er[y0:y1,x0:x1],"RGBA").save(imgdir/f'{r["uid"]}.png')
CW=360;PH=170;LH=76;font=ImageFont.load_default()
for start in range(0,len(review),9):
 batch=review[start:start+9]
 sheet=Image.new("RGB",(CW*3,(PH+LH)*3),(40,40,40));d=ImageDraw.Draw(sheet)
 for j,r in enumerate(batch):
  im=Image.open(imgdir/f'{r["uid"]}.png').convert("RGBA")
  scale=min((CW-8)/im.width,(PH-8)/im.height)
  rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.NEAREST)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  x=(j%3)*CW;y=(j//3)*(PH+LH);sheet.paste(bg.convert("RGB"),(x,y))
  d.rectangle((x,y+PH,x+CW,y+PH+LH),fill=(15,15,15))
  d.text((x+4,y+PH+3),f'{r["uid"]} {r["arc_path"]}:{r["member_index"]} score={r["score"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),r["texture_name"].split("\\")[-1][:48],fill=(210,210,210),font=font)
  d.text((x+4,y+PH+31),f'{r["target_node_name"]} / {r["animation_name"][:25]}',fill=(180,180,180),font=font)
  d.text((x+4,y+PH+45),f't={r["key_time"]} rect={r["rect"]}',fill=(150,150,150),font=font)
 sheet.save(sheetdir/f"ANIM_JPN_{start//9+1:02d}.jpg",quality=93)

print(json.dumps({"findings":len(findings),"sheets":(len(review)+8)//9,"top":findings[:40]},indent=2))
