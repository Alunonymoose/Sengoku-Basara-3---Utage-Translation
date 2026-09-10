import sys
sys.path.insert(0,r"E:\Utage Patching New\_codex_select_menu\quest_v3")
from common import *
W=Path(__file__).parent
from codec_v4 import patch_bc3_rect
from PIL import ImageFilter
j=arc.parse_arc(ROM/'jpn/quest/menu.arc');raw=arc.unpack(j.entries[35]);out=raw
from PIL import ImageDraw
master=Image.open(W/'menu_lettering_key.png').convert('RGBA');arr=np.array(master);r,g,b=arr[:,:,0].astype(int),arr[:,:,1].astype(int),arr[:,:,2].astype(int)
possible=(r>155)&(b>155)&(g<105)&(np.abs(r-b)<100)
padded=Image.new('L',(master.width+2,master.height+2),255);padded.paste(Image.fromarray(possible.astype('uint8')*255),(1,1));ImageDraw.floodfill(padded,(0,0),127)
bg=(np.array(padded)[1:-1,1:-1]==127)|((r>220)&(b>220)&(g<55))
fg=~bg
fg=np.asarray(Image.fromarray(fg.astype('uint8')*255).filter(ImageFilter.MinFilter(3)))>0
arr[:,:,3]=fg.astype('uint8')*255;arr[~fg,:3]=0;master=Image.fromarray(arr)
master.save(W/'menu_lettering_sprites.png')
# Native UV slots; all text changes bounded by their aligned physical cells.
bands=[(0,207),(207,397),(397,576),(576,765),(765,955),(955,1090),(1090,1220),(1220,1380),(1380,1536)]
rects=[(0,0,288,112),(0,120,288,240),(0,240,288,360),(0,360,288,480),(0,480,288,600),(704,400,924,476),(704,480,924,556),(624,640,884,776),(0,832,120,896)]
texts=["HEROES' STORY","UNIFICATION","JAPAN'S EVENT","VERSUS","QUICK BATTLES","PLAYER 1","PLAYER 2","DEPLOY","BATTLE"]
original=unpack_color(decode(raw));reports=[]
# Reuse native four-diamond badge, cleaning only its CPU lettering interior.
badge=original.crop((704,560,928,640));ba=np.array(badge)
for yy in range(21,57):
 t=(yy-20)/37
 ba[yy,42:192,:3]=((1-t)*ba[20,42:192,:3]+t*ba[57,42:192,:3]).astype('uint8')
badge=Image.fromarray(ba)
for k,((y0,y1),rect,txt) in enumerate(zip(bands,rects,texts)):
 sprite=master.crop((0,y0,master.width,y1))
 # Drop isolated keying dust and fragments from neighbouring rows.
 aa=np.array(sprite.getchannel('A'));seen=np.zeros(aa.shape,bool)
 for sy,sx in zip(*np.where(aa>0)):
  if seen[sy,sx]:continue
  stack=[(sy,sx)];seen[sy,sx]=True;part=[]
  while stack:
   cy,cx=stack.pop();part.append((cy,cx))
   for ny,nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
    if 0<=ny<aa.shape[0] and 0<=nx<aa.shape[1] and aa[ny,nx] and not seen[ny,nx]:seen[ny,nx]=True;stack.append((ny,nx))
  if len(part)<600:
   for cy,cx in part:aa[cy,cx]=0
 sprite.putalpha(Image.fromarray(aa));bb=sprite.getchannel('A').point(lambda v:255 if v>=100 else 0).getbbox();sprite=sprite.crop(bb)
 w,h=rect[2]-rect[0],rect[3]-rect[1];mw,mh=(w-12,h-12)
 if k in (5,6):mw,mh=180,38
 sc=min(mw/sprite.width,mh/sprite.height);sprite=sprite.resize((round(sprite.width*sc),round(sprite.height*sc)),Image.Resampling.LANCZOS)
 if k<5:sprite=sprite.resize((sprite.width,80),Image.Resampling.LANCZOS)
 cell=Image.new('RGBA',(w,h),(0,0,0,0))
 if k in (5,6):
  backing=badge.resize((w,h),Image.Resampling.LANCZOS)
  if k==5:
   hv=np.array(backing.convert('HSV'));hv[:,:,0]=(hv[:,:,0].astype(int)+150)%256;co=Image.fromarray(hv,'HSV').convert('RGBA');co.putalpha(backing.getchannel('A'));backing=co
  cell.alpha_composite(backing)
 sprite.putalpha(sprite.getchannel('A').point(lambda v:0 if v<24 else v))
 sprite.save(W/f'sprite_{k}.png')
 cell.alpha_composite(sprite,((w-sprite.width)//2,(h-sprite.height)//2))
 cell.save(W/f'cell_{k}.png')
 im=decode(out);im.paste(pack_color(cell),rect[:2]);out=patch_bc3_rect(out,im,rect)
 reports.append(dict(text=txt,rect=rect,source_band=[y0,y1],size=sprite.size))
# Untouched areas of the source atlas are preserved byte-for-byte.
(W/'charasele_v4.tex').write_bytes(out);preview(unpack_color(decode(out)),W/'CHARASELE_V4_PREVIEW.png');(W/'CHARASELE_BUILD.json').write_text(json.dumps(dict(source_sha256=arc.sha256(raw),sha256=arc.sha256(out),cells=reports),indent=2))
print(json.dumps(reports,indent=2))
