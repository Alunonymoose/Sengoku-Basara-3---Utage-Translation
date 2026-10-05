
from pathlib import Path
import csv,json,sys,importlib.util,collections,hashlib
from PIL import Image,ImageDraw,ImageFont

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
SH=Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
rows=list(csv.DictReader(open(OUT/"LAYOUT_REFERENCED_TEXTURE_AUDIT.csv",encoding="utf-8-sig")))
rows=[r for r in rows if r["jpn_state"]=="DIFF" and r["sh_state"]=="DIFF"]

# Dedup equivalent comparison tuple by current hash + SH path/name (one representative live consumer).
groups={}
for r in rows:
 k=(r["eng_sha256"],r["arc_path"].lower(),r["texture_name"].lower())
 if k not in groups:groups[k]=r
rows=sorted(groups.values(),key=lambda r:(r["arc_path"].lower(),int(r["member_index"]),r["texture_name"].lower()))

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

records=[]
imgdir=OUT/"sh_compare_png";sheetdir=OUT/"sh_compare_sheets"
imgdir.mkdir(exist_ok=True);sheetdir.mkdir(exist_ok=True)
for r in rows:
 rel=r["arc_path"].replace("\\","/")
 ep=ENG/rel;jp=JPN/rel;sp=SH/rel
 if not (jp.exists() and sp.exists()):continue
 try:
  ea=pa(ep);ja=pa(jp);sa=pa(sp)
  ee=find(ea,r["texture_name"]);je=find(ja,r["texture_name"]);se=find(sa,r["texture_name"])
  if not(ee and je and se):continue
  er=xet.decode_display(unpack_entry(ee));jr=xet.decode_display(unpack_entry(je));sr=xet.decode_display(unpack_entry(se))
  if er.shape!=jr.shape or er.shape!=sr.shape:continue
 except:continue
 cons=json.loads(r["consumers"])
 valid=[]
 for c in cons:
  x0,y0,x1,y1=map(int,c["src"])
  if 0<=x0<x1<=er.shape[1] and 0<=y0<y1<=er.shape[0]:
   valid.append(((x1-x0)*(y1-y0),(x0,y0,x1,y1),c))
 if not valid:continue
 valid.sort(reverse=True,key=lambda x:x[0]);_,rect,c=valid[0]
 x0,y0,x1,y1=rect
 uid=f"S{len(records)+1:03d}"
 for lab,arr in [("ENG",er),("JPN",jr),("SH",sr)]:
  Image.fromarray(arr[y0:y1,x0:x1],"RGBA").save(imgdir/f"{uid}_{lab}.png")
 records.append({
  "uid":uid,"arc_path":rel,"member_index":int(r["member_index"]),"texture_name":r["texture_name"],
  "rect":list(rect),"consumer":c,"current_sha256":r["eng_sha256"],
  "sh_raw_sha256":hashlib.sha256(unpack_entry(se)).hexdigest(),
  "crop_size":[x1-x0,y1-y0]
 })

(OUT/"SH_OFFICIAL_COMPARISON_REVIEW.json").write_text(json.dumps(records,indent=2),encoding="utf-8")

CW=330;PH=180;LH=70;cols=3;font=ImageFont.load_default()
# one comparison per row; 5 comparisons per sheet -> tall but readable
for start in range(0,len(records),5):
 batch=records[start:start+5]
 sheet=Image.new("RGB",(CW*3,(PH+LH)*len(batch)),(40,40,40));d=ImageDraw.Draw(sheet)
 for rr,r in enumerate(batch):
  y=rr*(PH+LH)
  for cc,lab in enumerate(("ENG","JPN","SH")):
   im=Image.open(imgdir/f'{r["uid"]}_{lab}.png').convert("RGBA")
   scale=min((CW-8)/im.width,(PH-8)/im.height)
   rim=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
   bg=Image.new("RGBA",(CW,PH),(96,96,96,255));bg.alpha_composite(rim,((CW-rim.width)//2,(PH-rim.height)//2))
   x=cc*CW;sheet.paste(bg.convert("RGB"),(x,y))
   d.text((x+4,y+4),lab,fill=(255,220,120),font=font)
  d.rectangle((0,y+PH,CW*3,y+PH+LH),fill=(15,15,15))
  d.text((5,y+PH+4),f'{r["uid"]} {r["arc_path"]}:{r["member_index"]}',fill="white",font=font)
  d.text((5,y+PH+18),r["texture_name"].split("\\")[-1],fill=(205,205,205),font=font)
  d.text((5,y+PH+32),f'{r["consumer"]["node_name"]} crop={r["rect"]}',fill=(175,175,175),font=font)
 p=sheetdir/f"SH_COMPARE_{start//5+1:02d}.jpg";sheet.save(p,quality=94)
print(json.dumps({"comparisons":len(records),"sheets":(len(records)+4)//5,"folder":str(sheetdir)},indent=2))
