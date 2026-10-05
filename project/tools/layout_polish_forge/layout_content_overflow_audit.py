
from pathlib import Path
import sys,json,collections,importlib.util,hashlib,math
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
from layout import is_layout,parse_layout
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"));xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

cache={}
def pa(p):
 k=str(p)
 if k not in cache:cache[k]=parse_arc(p)
 return cache[k]

usage=collections.defaultdict(lambda:collections.defaultdict(list))
for p in sorted(ROOT.rglob("*.arc"),key=lambda x:str(x.relative_to(ROOT)).lower()):
 try:a=pa(p)
 except:continue
 rel=str(p.relative_to(ROOT)).replace("\\","/")
 for e in a.entries:
  if e.type_hash!=0x60DD1B16 and not e.name.lower().endswith(".lsp"):continue
  try:
   raw=unpack_entry(e)
   if not is_layout(raw):continue
   lay=parse_layout(raw,e.name)
  except:continue
  for n in lay.nodes:
   if n.node_type not in (2,3) or not n.texture:continue
   key=n.texture.lower()
   usage[rel][key].append(("base",tuple(map(int,n.source_rect())),e.name,n.index,n.name))
   for an in lay.animations:
    tgt=lay.animation_target(an)
    if not tgt or tgt.index!=n.index:continue
    for ch in an.channels:
     if ch.name!="uv_rect":continue
     for k in ch.keys:
      vals=list(k.values)
      if len(vals)>=4:
       x,y,w,h=vals[:4]
       rect=(int(round(x*2)),int(round(y*2)),int(round((x+w)*2)),int(round((y+h)*2)))
       usage[rel][key].append((f"anim:{an.index}@{k.time}",rect,e.name,n.index,n.name))

findings=[]
imgdir=OUT/"layout_overflow_png";imgdir.mkdir(exist_ok=True)
for rel,texmap in usage.items():
 ep=ROOT/rel;jp=JPN/rel
 try:ea=pa(ep)
 except:continue
 ja=None
 if jp.exists():
  try:ja=pa(jp)
  except:ja=None
 byname={e.name.lower():e for e in ea.entries}
 jby={e.name.lower():e for e in ja.entries} if ja else {}
 for name,rects in texmap.items():
  ee=byname.get(name)
  if not ee:continue
  try:er=xet.decode_display(unpack_entry(ee))
  except:continue
  h,w=er.shape[:2]
  mask=np.zeros((h,w),dtype=bool)
  valid=[]
  for kind,rect,lay,ni,nn in rects:
   x0,y0,x1,y1=rect
   x0=max(0,min(w,x0));x1=max(0,min(w,x1));y0=max(0,min(h,y0));y1=max(0,min(h,y1))
   if x1>x0 and y1>y0:
    mask[y0:y1,x0:x1]=True;valid.append((kind,(x0,y0,x1,y1),lay,ni,nn))
  if not valid:continue
  ea_alpha=er[...,3]>16
  evis=int(ea_alpha.sum())
  if evis==0:continue
  eoutside=float((ea_alpha & ~mask).sum())/evis

  jr=None;jout=None
  je=jby.get(name)
  if je:
   try:
    jr=xet.decode_display(unpack_entry(je))
    if jr.shape==er.shape:
     jaa=jr[...,3]>16;jvis=int(jaa.sum())
     if jvis:jout=float((jaa & ~mask).sum())/jvis
   except:jr=None

  score=0;reasons=[]
  if eoutside>0.08:
   score+=min(60,eoutside*100);reasons.append("ENG_VISIBLE_OUTSIDE_LAYOUT_SAMPLES")
  if jout is not None and eoutside>jout+0.08:
   score+=min(50,(eoutside-jout)*120);reasons.append("ENG_EXCEEDS_JPN_OUTSIDE")

  edge_hits=0;j_edge_hits=0
  for _,(x0,y0,x1,y1),_,_,_ in valid:
   if x1-x0<4 or y1-y0<4:continue
   em=ea_alpha[y0:y1,x0:x1]
   eb=np.concatenate([em[:2,:].ravel(),em[-2:,:].ravel(),em[:,:2].ravel(),em[:,-2:].ravel()])
   edge_hits+=int(eb.sum())
   if jr is not None and jr.shape==er.shape:
    jm=(jr[...,3]>16)[y0:y1,x0:x1]
    jb=np.concatenate([jm[:2,:].ravel(),jm[-2:,:].ravel(),jm[:,:2].ravel(),jm[:,-2:].ravel()])
    j_edge_hits+=int(jb.sum())
  if edge_hits>j_edge_hits+20:
   score+=min(30,(edge_hits-j_edge_hits)/10);reasons.append("ENG_TOUCHES_SAMPLE_BOUNDARY")
  if score<18:continue

  uid=f"O{len(findings)+1:03d}"
  Image.fromarray(er,"RGBA").save(imgdir/f"{uid}_ENG.png")
  if jr is not None and jr.shape==er.shape:Image.fromarray(jr,"RGBA").save(imgdir/f"{uid}_JPN.png")
  findings.append({
   "uid":uid,"score":round(score,2),"arc_path":rel,"member_index":ee.index,"texture_name":ee.name,
   "size":[w,h],"eng_outside_ratio":round(eoutside,4),"jpn_outside_ratio":round(jout,4) if jout is not None else None,
   "edge_hits":edge_hits,"jpn_edge_hits":j_edge_hits,"reasons":reasons,
   "sample_rects":[{"kind":x[0],"rect":x[1],"layout":x[2],"node_index":x[3],"node_name":x[4]} for x in valid]
  })
findings.sort(key=lambda x:(-x["score"],x["arc_path"].lower(),x["member_index"]))
(OUT/"LAYOUT_CONTENT_OVERFLOW_AUDIT.json").write_text(json.dumps(findings,indent=2),encoding="utf-8")

sheetdir=OUT/"layout_overflow_sheets";sheetdir.mkdir(exist_ok=True)
review=findings[:36];font=ImageFont.load_default();COLS=3;ROWS=3;CW=360;PH=230;LH=66;CELLH=PH+LH
for start in range(0,len(review),9):
 batch=review[start:start+9];sheet=Image.new("RGB",(COLS*CW,ROWS*CELLH),(38,38,38));d=ImageDraw.Draw(sheet)
 for j,r in enumerate(batch):
  rr=j//COLS;cc=j%COLS;x=cc*CW;y=rr*CELLH
  im=Image.open(imgdir/f'{r["uid"]}_ENG.png').convert("RGBA")
  ov=im.copy();od=ImageDraw.Draw(ov)
  for sr in r["sample_rects"]:
   od.rectangle(tuple(sr["rect"]),outline=(255,0,0,255),width=max(1,im.width//256))
  scale=min((CW-8)/ov.width,(PH-8)/ov.height)
  rim=ov.resize((max(1,int(ov.width*scale)),max(1,int(ov.height*scale))),Image.Resampling.NEAREST)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  sheet.paste(bg.convert("RGB"),(x,y))
  d.rectangle((x,y+PH,x+CW,y+CELLH),fill=(15,15,15))
  d.text((x+4,y+PH+3),f'{r["uid"]} score={r["score"]} {r["arc_path"]}:{r["member_index"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),r["texture_name"].split("\\")[-1][:48],fill=(205,205,205),font=font)
  d.text((x+4,y+PH+31),f'outside ENG={r["eng_outside_ratio"]} JPN={r["jpn_outside_ratio"]}',fill=(175,175,175),font=font)
  d.text((x+4,y+PH+45),",".join(r["reasons"]),fill=(150,150,150),font=font)
 p=sheetdir/f"OVERFLOW_{start//9+1:02d}.jpg";sheet.save(p,quality=94)
print(json.dumps({"findings":len(findings),"sheets":math.ceil(min(36,len(findings))/9) if findings else 0,
"top20":[{k:r[k] for k in ("uid","score","arc_path","member_index","texture_name","eng_outside_ratio","jpn_outside_ratio","reasons")} for r in findings[:20]]},indent=2))
