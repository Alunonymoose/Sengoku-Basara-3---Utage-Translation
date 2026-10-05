
from pathlib import Path
import sys,json,collections,importlib.util,math
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
   usage[rel][n.texture.lower()].append({
      "kind":"base","rect":tuple(map(int,n.source_rect())),
      "layout":e.name,"node_index":n.index,"node_name":n.name
   })
   for an in lay.animations:
    tgt=lay.animation_target(an)
    if not tgt or tgt.index!=n.index:continue
    for ch in an.channels:
     if ch.name!="uv_rect":continue
     for k in ch.keys:
      vals=list(k.values)
      if len(vals)>=4:
       x,y,w,h=vals[:4]
       usage[rel][n.texture.lower()].append({
        "kind":f"anim:{an.index}@{k.time}",
        "rect":(int(round(x*2)),int(round(y*2)),int(round((x+w)*2)),int(round((y+h)*2))),
        "layout":e.name,"node_index":n.index,"node_name":n.name
       })

findings=[]
imgdir=OUT/"boundary_continuation_png";imgdir.mkdir(exist_ok=True)
for rel,tmap in usage.items():
 ep=ROOT/rel;jp=JPN/rel
 try:ea=pa(ep)
 except:continue
 ja=None
 if jp.exists():
  try:ja=pa(jp)
  except:pass
 eb={e.name.lower():e for e in ea.entries}
 jb={e.name.lower():e for e in ja.entries} if ja else {}
 for name,uses in tmap.items():
  ee=eb.get(name)
  if not ee:continue
  try:er=xet.decode_display(unpack_entry(ee)); ea_mask=er[...,3]>20
  except:continue
  jr=None;jm=None
  je=jb.get(name)
  if je:
   try:
    jr=xet.decode_display(unpack_entry(je))
    if jr.shape==er.shape:jm=jr[...,3]>20
   except:pass
  H,W=ea_mask.shape
  # unique rectangles only
  seen=set()
  for u in uses:
   rect=tuple(u["rect"])
   if rect in seen:continue
   seen.add(rect)
   x0,y0,x1,y1=rect
   if not (0<=x0<x1<=W and 0<=y0<y1<=H):continue
   # Need an actual external region beside boundary.
   sides=[]
   pad=12
   inner=3
   if x1<W:
    inside=ea_mask[y0:y1,max(x0,x1-inner):x1]
    outside=ea_mask[y0:y1,x1:min(W,x1+pad)]
    ji=jm[y0:y1,max(x0,x1-inner):x1] if jm is not None else None
    jo=jm[y0:y1,x1:min(W,x1+pad)] if jm is not None else None
    sides.append(("RIGHT",inside,outside,ji,jo))
   if x0>0:
    inside=ea_mask[y0:y1,x0:min(x1,x0+inner)]
    outside=ea_mask[y0:y1,max(0,x0-pad):x0]
    ji=jm[y0:y1,x0:min(x1,x0+inner)] if jm is not None else None
    jo=jm[y0:y1,max(0,x0-pad):x0] if jm is not None else None
    sides.append(("LEFT",inside,outside,ji,jo))
   if y1<H:
    inside=ea_mask[max(y0,y1-inner):y1,x0:x1]
    outside=ea_mask[y1:min(H,y1+pad),x0:x1]
    ji=jm[max(y0,y1-inner):y1,x0:x1] if jm is not None else None
    jo=jm[y1:min(H,y1+pad),x0:x1] if jm is not None else None
    sides.append(("BOTTOM",inside,outside,ji,jo))
   if y0>0:
    inside=ea_mask[y0:min(y1,y0+inner),x0:x1]
    outside=ea_mask[max(0,y0-pad):y0,x0:x1]
    ji=jm[y0:min(y1,y0+inner),x0:x1] if jm is not None else None
    jo=jm[max(0,y0-pad):y0,x0:x1] if jm is not None else None
    sides.append(("TOP",inside,outside,ji,jo))

   for side,inside,outside,ji,jo in sides:
    # boundary-crossing evidence: alpha on both sides, with outside continuation substantial.
    ins=float(inside.mean()) if inside.size else 0
    out=float(outside.mean()) if outside.size else 0
    jins=float(ji.mean()) if ji is not None and ji.size else None
    jout=float(jo.mean()) if jo is not None and jo.size else None
    if ins<0.03 or out<0.02:continue
    delta=out-(jout or 0) if jout is not None else out
    # Require more continuation than JPN, or very strong continuation if no JPN.
    if jout is not None and delta<0.025:continue
    if jout is None and out<0.08:continue
    score=(ins*30)+(out*100)+(max(0,delta)*120)
    findings.append({
      "score":round(score,2),"arc_path":rel,"member_index":ee.index,"texture_name":ee.name,
      "layout":u["layout"],"node_index":u["node_index"],"node_name":u["node_name"],
      "rect":rect,"side":side,
      "eng_inside_edge":round(ins,4),"eng_outside_adjacent":round(out,4),
      "jpn_inside_edge":round(jins,4) if jins is not None else None,
      "jpn_outside_adjacent":round(jout,4) if jout is not None else None,
      "outside_delta":round(delta,4)
    })

# dedup exact resource/rect/side keeping highest score
best={}
for r in findings:
 k=(r["arc_path"],r["member_index"],r["rect"],r["side"])
 if k not in best or r["score"]>best[k]["score"]:best[k]=r
findings=sorted(best.values(),key=lambda r:(-r["score"],r["arc_path"].lower(),r["member_index"]))
for i,r in enumerate(findings,1):r["uid"]=f"B{i:03d}"
(OUT/"BOUNDARY_CONTINUATION_AUDIT.json").write_text(json.dumps(findings,indent=2),encoding="utf-8")

# Create top 27 sheets with rect + offending adjacent boundary highlighted.
sheetdir=OUT/"boundary_continuation_sheets";sheetdir.mkdir(exist_ok=True)
for start in range(0,min(27,len(findings)),9):
 batch=findings[start:start+9];CW=360;PH=230;LH=70
 sheet=Image.new("RGB",(CW*3,(PH+LH)*3),(38,38,38));d=ImageDraw.Draw(sheet);font=ImageFont.load_default()
 for j,r in enumerate(batch):
  p=ROOT/r["arc_path"];a=pa(p);e=a.entries[int(r["member_index"])]
  im=Image.fromarray(xet.decode_display(unpack_entry(e)),"RGBA")
  ov=im.copy();od=ImageDraw.Draw(ov)
  x0,y0,x1,y1=r["rect"];od.rectangle((x0,y0,x1,y1),outline=(255,0,0,255),width=max(1,im.width//256))
  # mark adjacent strip in yellow
  pad=12
  if r["side"]=="RIGHT":adj=(x1,y0,min(im.width,x1+pad),y1)
  elif r["side"]=="LEFT":adj=(max(0,x0-pad),y0,x0,y1)
  elif r["side"]=="BOTTOM":adj=(x0,y1,x1,min(im.height,y1+pad))
  else:adj=(x0,max(0,y0-pad),x1,y0)
  od.rectangle(adj,outline=(255,255,0,255),width=max(1,im.width//256))
  scale=min((CW-8)/ov.width,(PH-8)/ov.height)
  rim=ov.resize((max(1,int(ov.width*scale)),max(1,int(ov.height*scale))),Image.Resampling.NEAREST)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  rr=j//3;cc=j%3;x=cc*CW;y=rr*(PH+LH);sheet.paste(bg.convert("RGB"),(x,y))
  d.rectangle((x,y+PH,x+CW,y+PH+LH),fill=(15,15,15))
  d.text((x+4,y+PH+3),f'{r["uid"]} score={r["score"]} {r["arc_path"]}:{r["member_index"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),r["texture_name"].split("\\")[-1][:48],fill=(205,205,205),font=font)
  d.text((x+4,y+PH+31),f'{r["node_name"]} {r["side"]} delta={r["outside_delta"]}',fill=(175,175,175),font=font)
  d.text((x+4,y+PH+45),f'ENG out={r["eng_outside_adjacent"]} JPN out={r["jpn_outside_adjacent"]}',fill=(150,150,150),font=font)
 sheet.save(sheetdir/f"BOUNDARY_{start//9+1:02d}.jpg",quality=94)

print(json.dumps({"findings":len(findings),"top":[r for r in findings[:25]]},indent=2))
