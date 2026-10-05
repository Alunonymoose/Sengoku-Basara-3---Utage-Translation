
from pathlib import Path
import json,sys,importlib.util,hashlib,collections,math
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
SH=Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
metrics=json.loads((OUT/"LAYOUT_CUSTOM_QUALITY_METRICS.json").read_text(encoding="utf-8"))[:35]

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
 low=name.lower();h=[e for e in a.entries if e.name.lower()==low]
 return h[0] if len(h)==1 else None

names={r["texture_name"].lower() for r in metrics}
sh_index=collections.defaultdict(list)
for p in SH.rglob("*.arc"):
 try:a=pa(p)
 except:continue
 rel=str(p.relative_to(SH)).replace("\\","/")
 for e in a.entries:
  if e.name.lower() in names:
   raw=unpack_entry(e)
   sh_index[e.name.lower()].append((rel,e.index,raw,hashlib.sha256(raw).hexdigest()))

tripdir=OUT/"quality_sh_donor_png";tripdir.mkdir(exist_ok=True)
records=[]
for r in metrics:
 rel=r["arc_path"]; name=r["texture_name"]; rect=r.get("crop_rect")
 try:
  ea=pa(ROOT/rel);ee=find(ea,name); er=xet.decode_display(unpack_entry(ee))
 except:continue
 jr=None
 if (JPN/rel).exists():
  try:
   ja=pa(JPN/rel);je=find(ja,name)
   if je:jr=xet.decode_display(unpack_entry(je))
  except:pass
 donors=sh_index.get(name.lower(),[])
 # choose first unique hash donor
 seen=set();unique=[]
 for rels,idx,raw,h in donors:
  if h in seen:continue
  seen.add(h);unique.append((rels,idx,raw,h))
 shims=[]
 for k,(rels,idx,raw,h) in enumerate(unique[:3],1):
  try:arr=xet.decode_display(raw)
  except:continue
  shims.append((rels,idx,h,arr))
 def crop(arr):
  if arr is None:return None
  if rect:
   x0,y0,x1,y1=map(int,rect)
   if 0<=x0<x1<=arr.shape[1] and 0<=y0<y1<=arr.shape[0]:
    return arr[y0:y1,x0:x1]
  return arr
 ec=crop(er);jc=crop(jr) if jr is not None else None
 panels=[("ENG CURRENT",ec,rel)]
 if jc is not None:panels.append(("JPN",jc,rel))
 for rels,idx,h,arr in shims:panels.append((f"SH {rels}:{idx}",crop(arr),h[:12]))
 records.append({**r,"sh_donors":[{"arc":x[0],"idx":x[1],"hash":x[2]} for x in shims]})
 # sheet one record per image
 CW=320;PH=230;LH=54;cols=len(panels)
 sheet=Image.new("RGB",(CW*cols,PH+LH),(45,45,45));d=ImageDraw.Draw(sheet);font=ImageFont.load_default()
 for j,(label,arr,sub) in enumerate(panels):
  x=j*CW
  im=Image.fromarray(arr,"RGBA")
  scale=min((CW-8)/im.width,(PH-8)/im.height)
  rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
  bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
  sheet.paste(bg.convert("RGB"),(x,0))
  d.rectangle((x,PH,x+CW,PH+LH),fill=(14,14,14))
  d.text((x+4,PH+3),label,fill="white",font=font)
  d.text((x+4,PH+17),str(sub)[:48],fill=(180,180,180),font=font)
 d.text((4,4),f'{r["uid"]} score={r["score"]} {name.split(chr(92))[-1]}',fill=(255,220,120),font=font)
 out=tripdir/f'{r["uid"]}_TRIPLE.jpg';sheet.save(out,quality=94)
(OUT/"QUALITY_SH_DONOR_AUDIT.json").write_text(json.dumps(records,indent=2),encoding="utf-8")
print(json.dumps({"records":len(records),"with_sh_same_name":sum(bool(r["sh_donors"]) for r in records),
"top":[{"uid":r["uid"],"score":r["score"],"name":r["texture_name"],"sh_donors":r["sh_donors"]} for r in records[:25]]},indent=2))
