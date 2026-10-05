
from pathlib import Path
import json,sys,importlib.util,hashlib,math
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
records=json.loads((OUT/"LAYOUT_CUSTOM_REVIEW.json").read_text(encoding="utf-8"))

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"));xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

cache={}
def pa(p):
 k=str(p)
 if k not in cache:cache[k]=parse_arc(p)
 return cache[k]
def find(a,name):
 low=name.lower()
 hits=[e for e in a.entries if e.name.lower()==low]
 return hits[0] if len(hits)==1 else None

def metrics(arr):
 a=arr[...,3].astype(np.float32)/255
 rgb=arr[...,:3].astype(np.float32)
 lum=0.2126*rgb[...,0]+0.7152*rgb[...,1]+0.0722*rgb[...,2]
 # weighted gradient over visible pixels
 gx=np.abs(np.diff(lum,axis=1)); gy=np.abs(np.diff(lum,axis=0))
 wx=np.minimum(a[:,:-1],a[:,1:]); wy=np.minimum(a[:-1,:],a[1:,:])
 sharp=(float((gx*wx).sum()+ (gy*wy).sum()) / max(1.0,float(wx.sum()+wy.sum())))
 vis=a>0.06
 semi=(a>0.03)&(a<0.95)
 opaque=a>=0.95
 h,w=a.shape
 border=np.zeros_like(vis);border[:2,:]=1;border[-2:,:]=1;border[:,:2]=1;border[:,-2:]=1
 border_touch=float((vis&border).sum())/max(1,int(vis.sum()))
 return {
   "visible_coverage":float(vis.mean()),
   "opaque_coverage":float(opaque.mean()),
   "semi_fraction_visible":float(semi.sum())/max(1,int(vis.sum())),
   "border_touch_visible":border_touch,
   "sharpness":sharp
 }

rows=[]
imgdir=OUT/"quality_metric_png";imgdir.mkdir(exist_ok=True)
for r in records:
 rel=r["arc_path"]; ep=ROOT/rel; jp=JPN/rel
 if not jp.exists():continue
 try:
  ea=pa(ep); ja=pa(jp)
  ee=find(ea,r["texture_name"]); je=find(ja,r["texture_name"])
  if ee is None or je is None:continue
  er=xet.decode_display(unpack_entry(ee)); jr=xet.decode_display(unpack_entry(je))
  if er.shape!=jr.shape:continue
 except Exception:continue
 rect=r.get("crop_rect")
 if rect:
  x0,y0,x1,y1=map(int,rect)
  if not (0<=x0<x1<=er.shape[1] and 0<=y0<y1<=er.shape[0]):continue
  ec=er[y0:y1,x0:x1]; jc=jr[y0:y1,x0:x1]
 else:
  ec=er;jc=jr
 em=metrics(ec); jm=metrics(jc)
 sharp_ratio=em["sharpness"]/max(jm["sharpness"],1e-6)
 semi_delta=em["semi_fraction_visible"]-jm["semi_fraction_visible"]
 cover_ratio=em["visible_coverage"]/max(jm["visible_coverage"],1e-6)
 # Heuristic anomaly score. High = worth human review, not automatic defect.
 score=0
 reasons=[]
 if sharp_ratio<0.72 and jm["sharpness"]>4:
  score+=(0.72-sharp_ratio)*100;reasons.append("ENG_SOFT")
 if em["border_touch_visible"]>0.025 and em["border_touch_visible"]>jm["border_touch_visible"]*1.5+0.005:
  score+=min(25,em["border_touch_visible"]*150);reasons.append("ENG_TOUCHES_CROP_EDGE")
 if semi_delta>0.12:
  score+=min(25,semi_delta*80);reasons.append("EXCESS_ALPHA_FRINGE")
 if cover_ratio>1.8 or cover_ratio<0.55:
  score+=15;reasons.append("COVERAGE_SHIFT")
 if score<=0:continue
 uid=r["uid"]
 Image.fromarray(ec,"RGBA").save(imgdir/f"{uid}_ENG.png")
 Image.fromarray(jc,"RGBA").save(imgdir/f"{uid}_JPN.png")
 rows.append({
   "uid":uid,"score":round(score,2),"arc_path":rel,"member_index":r["member_index"],
   "texture_name":r["texture_name"],"crop_rect":rect,
   "sharp_ratio":round(sharp_ratio,3),"eng":em,"jpn":jm,
   "cover_ratio":round(cover_ratio,3),"reasons":reasons
 })
rows.sort(key=lambda x:(-x["score"],x["arc_path"].lower(),x["member_index"]))
(OUT/"LAYOUT_CUSTOM_QUALITY_METRICS.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")

# top 45 review sheets
review=rows[:45];sheetdir=OUT/"quality_metric_sheets";sheetdir.mkdir(exist_ok=True)
COLS=3;ROWS=3;CW=360;PH=210;LH=68;CELLH=PH+LH;font=ImageFont.load_default()
for start in range(0,len(review),9):
 batch=review[start:start+9]
 sheet=Image.new("RGB",(COLS*CW,ROWS*CELLH),(38,38,38));d=ImageDraw.Draw(sheet)
 for j,r in enumerate(batch):
  rr=j//COLS;cc=j%COLS;x=cc*CW;y=rr*CELLH
  ei=Image.open(imgdir/f'{r["uid"]}_ENG.png').convert("RGBA")
  ji=Image.open(imgdir/f'{r["uid"]}_JPN.png').convert("RGBA")
  for pane,im,label in [(0,ei,"ENG LIVE CROP"),(1,ji,"JPN SAME CROP")]:
   pw=CW//2;scale=min((pw-8)/im.width,(PH-8)/im.height)
   rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
   bg=Image.new("RGBA",(pw,PH),(96,96,96,255));bg.alpha_composite(rim,((pw-rim.width)//2,(PH-rim.height)//2))
   sheet.paste(bg.convert("RGB"),(x+pane*pw,y));d.text((x+pane*pw+3,y+3),label,fill=(255,220,120),font=font)
  d.rectangle((x,y+PH,x+CW,y+CELLH),fill=(15,15,15))
  d.text((x+4,y+PH+3),f'{r["uid"]} score={r["score"]} {r["arc_path"]}:{r["member_index"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),r["texture_name"].split("\\")[-1][:49],fill=(205,205,205),font=font)
  d.text((x+4,y+PH+31),f'sharp={r["sharp_ratio"]} coverage={r["cover_ratio"]}',fill=(175,175,175),font=font)
  d.text((x+4,y+PH+45),",".join(r["reasons"]),fill=(155,155,155),font=font)
 p=sheetdir/f"QUALITY_{start//9+1:02d}.jpg";sheet.save(p,quality=94)
print(json.dumps({"anomalies":len(rows),"top45_sheets":math.ceil(min(45,len(rows))/9),
                  "top20":[{k:r[k] for k in ("uid","score","arc_path","member_index","texture_name","sharp_ratio","cover_ratio","reasons")} for r in rows[:20]]},indent=2))
