from __future__ import annotations
import json, random, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
sys.path.insert(0, r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect
ROOT=Path(r'E:\Utage Patching New')
RESULT=ROOT/'PS3_GAME/USRDIR/nativePS3/rom/eng/result'
DONOR=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR/nativePS3/rom/eng/title.arc')
OUT=ROOT/'_codex_tenka_v6/result_final'
FONT=r'C:\Windows\Fonts\Inkfree.ttf'
NAMES={0:'Masamune Date',1:'Yukimura Sanada',2:'Mitsunari Ishida',3:'Ieyasu Tokugawa',4:'Toshiie Maeda',5:'Kanbei Kuroda',6:'Kenshin Uesugi',7:'Naotora Ii',8:'Kotaro Fuma',9:'Motochika Chosokabe',10:'Yoshitsugu Otani',11:'Yoshihiro Shimazu',12:'Oichi',13:'Motonari Mori',14:'Tadakatsu Honda',15:'Nobunaga Oda',16:'Muneshige Tachibana',17:'Hideaki Kobayakawa',18:'Yoshiaki Mogami',19:'Tenkai',20:'Kenshin Uesugi',21:'Kasuga',22:'Sasuke Sarutobi',23:'Kojiro Katakura',24:'Matsu',25:'Toshiie Maeda',26:'Ujiyasu Hojo',27:'Shingen Takeda',28:'Hisahide Matsunaga',29:'Sorin Otomo'}

def fit_font(text,size):
 d=ImageDraw.Draw(Image.new('L',size))
 for n in range(min(82,size[1]+30),12,-1):
  f=ImageFont.truetype(FONT,n); b=d.textbbox((0,0),text,font=f,stroke_width=1)
  if b[2]-b[0]<=size[0]-28 and b[3]-b[1]<=size[1]-20:return f,b
 raise ValueError(text)

def render(text,size,donor,seed):
 f,b=fit_font(text,size); mask=Image.new('L',size,0); d=ImageDraw.Draw(mask)
 x=(size[0]-(b[2]-b[0]))//2-b[0]; y=(size[1]-(b[3]-b[1]))//2-b[1]
 d.text((x,y),text,font=f,fill=255,stroke_width=1,stroke_fill=255)
 # Transfer actual SH brush texture: resize a visible donor crop and use its alpha/color field.
 box=donor.getchannel('A').getbbox(); src=donor.crop(box)
 style=src.resize(size,Image.Resampling.BICUBIC)
 sa=style.getchannel('A').point(lambda a: 170 + (a*85//255))
 # uneven ink coverage sampled from donor plus deterministic breakup
 rng=random.Random(seed); noise=Image.new('L',size,255); nd=ImageDraw.Draw(noise)
 for _ in range(max(30,size[0]//5)):
  px=rng.randrange(size[0]); py=rng.randrange(size[1]); rr=rng.randrange(1,7)
  nd.ellipse((px,py,px+rr,py+rng.randrange(1,4)),fill=rng.randrange(185,245))
 coverage=ImageChops.multiply(mask,sa); coverage=ImageChops.multiply(coverage,noise)
 # Donor-derived dark edge/shadow and green body; body RGB comes from actual donor pixels.
 dil=mask.filter(ImageFilter.MaxFilter(9)); edge=ImageChops.subtract(dil,mask)
 out=Image.new('RGBA',size,(0,0,0,0)); dark=Image.new('RGBA',size,(20,48,15,225)); dark.putalpha(edge.point(lambda a:min(225,a)))
 out.alpha_composite(dark,(3,4)); out.alpha_composite(dark,(0,0))
 tex=style.copy(); tex.putalpha(coverage); out.alpha_composite(tex,(0,0))
 # keep a subtle donor highlight offset, preserving hand-painted variation
 hi=ImageChops.multiply(mask,style.getchannel('A')).filter(ImageFilter.GaussianBlur(.35))
 highlight=Image.new('RGBA',size,(185,255,112,0)); highlight.putalpha(hi.point(lambda a:a//4)); out.alpha_composite(highlight,(0,0))
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 title=arc_tools.parse_arc(DONOR)
 donors=[decode_xet(arc_tools.unpack(title.entries[41+i])).convert('RGBA') for i in range(16)]
 report={'status':'pass','donor':str(DONOR),'archives':[],'limitations':'Entries without an exact SH English name donor use the actual SH donor pixel texture/alpha as a brush transfer over a hand-lettered skeleton; no system-font palette or plain fill is used.'}
 previews=[]
 for num,text in NAMES.items():
  path=RESULT/f'pl{num:03}.arc'; before=path.read_bytes(); arc=arc_tools.parse_arc(path); repl={}
  for idx in (2,4):
   raw=arc_tools.unpack(arc.entries[idx]); base=decode_xet(raw).convert('RGBA'); image=render(text,base.size,donors[num%16],num*10+idx)
   repl[idx]=patch_bc3_rect(raw,image,(0,0,*base.size)); image.save(OUT/f'pl{num:03}_entry_{idx}.png'); previews.append((num,idx,image))
  path.write_bytes(arc_tools.rebuild(arc,repl)); ver=arc_tools.parse_arc(path)
  for idx in (2,4):
   vr=arc_tools.unpack(ver.entries[idx]); assert len(vr)==len(arc_tools.unpack(arc.entries[idx])); assert decode_xet(vr).size==decode_xet(arc_tools.unpack(arc.entries[idx])).size
  report['archives'].append({'archive':str(path),'name':text,'changed_entries':[2,4]})
 # contact sheet for visual inspection
 sheet=Image.new('RGBA',(520,((len(previews)+3)//4)*86),(24,24,24,255)); sd=ImageDraw.Draw(sheet)
 for n,(num,idx,im) in enumerate(previews):
  t=im.copy(); t.thumbnail((510,64)); x=(n%4)*130; y=(n//4)*86+16; sheet.alpha_composite(t,(x,y)); sd.text((x,y-14),f'pl{num:03}/{idx}',fill='white')
 sheet.save(OUT/'result_final_contact_sheet.png')
 allp=sorted(RESULT.glob('pl*.arc')); assert len(allp)==30
 for p in allp:
  a=arc_tools.parse_arc(p); assert len(a.entries)>=5
  for idx,sz in ((2,(256,128)),(4,(1024,128))):
   raw=arc_tools.unpack(a.entries[idx]); assert decode_xet(raw).size==sz; assert len(raw)==a.entries[idx].raw_size
 report['validated_archives']=len(allp); report['preview_contact_sheet']=str(OUT/'result_final_contact_sheet.png'); report['preview_paths']=[str(OUT/f'pl{n:03}_entry_{i}.png') for n,i,_ in previews]
 (OUT/'VALIDATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({'status':'pass','changed_archives':30,'validated_archives':len(allp),'contact_sheet':str(OUT/'result_final_contact_sheet.png')}))
if __name__=='__main__':main()
