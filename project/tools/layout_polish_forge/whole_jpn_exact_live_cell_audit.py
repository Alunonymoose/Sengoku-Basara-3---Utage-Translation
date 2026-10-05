
from pathlib import Path
import csv,json,collections,sys,importlib.util,hashlib
from PIL import Image,ImageDraw,ImageFont
import numpy as np

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
ROOT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
rows=list(csv.DictReader(open(ROOT/"LAYOUT_REFERENCED_TEXTURE_AUDIT.csv",encoding="utf-8-sig")))
exact=[r for r in rows if r["jpn_state"]=="EXACT"]
OUT=ROOT/"whole_jpn_exact_cells";OUT.mkdir(exist_ok=True)

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"))
xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

cache={}
def get_img(rel,idx):
 k=(rel,idx)
 if k in cache:return cache[k]
 p=ENG/rel
 try:
  a=parse_arc(p);e=a.entries[idx];raw=unpack_entry(e);arr=xet.decode_display(raw)
 except Exception:
  arr=None
 cache[k]=arr;return arr

# unique by texture hash + source rect; aggregate consumers/providers
groups={}
for r in exact:
 rel=r["arc_path"].replace("\\","/")
 idx=int(r["member_index"])
 try:cons=json.loads(r["consumers"])
 except:cons=[]
 for c in cons:
  src=c.get("src")
  if not src or len(src)!=4:continue
  rect=tuple(map(int,src))
  k=(r["eng_sha256"],rect)
  g=groups.setdefault(k,{
    "eng_sha256":r["eng_sha256"],"rect":list(rect),"providers":set(),"nodes":set(),
    "layouts":set(),"default_visible":False,"animated":False,
    "score":int(r["score"] or 0),"representative":(rel,idx,r["texture_name"])
  })
  g["providers"].add((rel,idx,r["texture_name"]))
  g["nodes"].add(str(c.get("node_name") or ""))
  g["layouts"].add(str(c.get("layout") or ""))
  g["default_visible"] |= bool(c.get("default_display"))
  g["animated"] |= bool(c.get("animated"))
  g["score"]=max(g["score"],int(r["score"] or 0))

items=[]
for g in groups.values():
 rel,idx,name=g["representative"];arr=get_img(rel,idx)
 if arr is None:continue
 H,W=arr.shape[:2];x0,y0,x1,y1=g["rect"]
 if not(0<=x0<x1<=W and 0<=y0<y1<=H):continue
 cell=arr[y0:y1,x0:x1]
 alpha=cell[...,3]>16
 vis=float(alpha.mean())
 if vis<0.006:continue
 # score useful review candidates; still save all.
 w=x1-x0;h=y1-y0
 textish={"text","title","name","page","mode","system","details","help","guide","label","rank","tassei","ichi","ni","rei","kakutoku","senme","win","lose","yes","no","lv","condition","urire","urikire"}
 bonus=0
 if g["default_visible"]:bonus+=20
 if g["animated"]:bonus+=5
 if 20<=w<=600 and 12<=h<=240:bonus+=10
 if any(any(t in n.lower() for t in textish) for n in g["nodes"]):bonus+=30
 priority=g["score"]+bonus
 uid=f"E{len(items)+1:04d}"
 Image.fromarray(cell,"RGBA").save(OUT/f"{uid}_CELL.png")
 items.append({
  "uid":uid,"priority":priority,"base_score":g["score"],
  "eng_sha256":g["eng_sha256"],"rect":g["rect"],"crop_size":[w,h],
  "visible_coverage":round(vis,4),"default_visible":g["default_visible"],"animated":g["animated"],
  "providers":[{"arc":p[0],"member_index":p[1],"texture_name":p[2]} for p in sorted(g["providers"])],
  "node_names":sorted(g["nodes"]),"layouts":sorted(g["layouts"])
 })

items.sort(key=lambda r:(-r["priority"],not r["default_visible"],r["providers"][0]["arc"].lower(),r["rect"]))
(ROOT/"WHOLE_JPN_EXACT_LIVE_CELLS.json").write_text(json.dumps(items,indent=2),encoding="utf-8")

# top 270 unique cells -> 30 sheets
sheetdir=ROOT/"whole_jpn_exact_sheets";sheetdir.mkdir(exist_ok=True)
CW=360;PH=180;LH=82;font=ImageFont.load_default()
review=items[:270]
for start in range(0,len(review),9):
 batch=review[start:start+9]
 sheet=Image.new("RGB",(CW*3,(PH+LH)*3),(40,40,40));d=ImageDraw.Draw(sheet)
 for j,r in enumerate(batch):
  rr=j//3;cc=j%3;x=cc*CW;y=rr*(PH+LH)
  im=Image.open(OUT/f'{r["uid"]}_CELL.png').convert("RGBA")
  scale=min((CW-8)/im.width,(PH-8)/im.height)
  rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.NEAREST)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  sheet.paste(bg.convert("RGB"),(x,y))
  d.rectangle((x,y+PH,x+CW,y+PH+LH),fill=(15,15,15))
  p=r["providers"][0]
  d.text((x+4,y+PH+3),f'{r["uid"]} pri={r["priority"]} {p["arc"]}:{p["member_index"]}',fill="white",font=font)
  d.text((x+4,y+PH+17),p["texture_name"].split("\\")[-1][:47],fill=(205,205,205),font=font)
  d.text((x+4,y+PH+31),f'rect={r["rect"]} vis={r["default_visible"]} providers={len(r["providers"])}',fill=(180,180,180),font=font)
  names=",".join(r["node_names"])
  d.text((x+4,y+PH+45),names[:52],fill=(155,155,155),font=font)
  if len(names)>52:d.text((x+4,y+PH+59),names[52:104],fill=(145,145,145),font=font)
 sheet.save(sheetdir/f"EXACT_JPN_{start//9+1:02d}.jpg",quality=94)

print(json.dumps({
 "audit_rows":len(rows),"whole_jpn_exact_rows":len(exact),
 "unique_visible_cells":len(items),"review_sheets":(len(review)+8)//9,
 "top":[{k:r[k] for k in ("uid","priority","rect","default_visible","animated","node_names","providers")} for r in items[:40]]
},indent=2))
