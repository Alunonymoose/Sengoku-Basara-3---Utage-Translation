import sys, json, struct, zipfile
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
V4=W.parent/'quest_v4'; O=W.parent/'quest_v5'
sys.path.insert(0,str(V4))
from codec_v4 import patch_bc3_rect
from PIL import ImageDraw,ImageFilter

def keyed(path,bands,overlap=0):
 im=Image.open(path).convert('RGBA');a=np.array(im);r,g,b=[a[:,:,i].astype(int) for i in range(3)]
 possible=(r>155)&(b>155)&(g<105)&(abs(r-b)<100)
 pad=Image.new('L',(im.width+2,im.height+2),255);pad.paste(Image.fromarray(possible.astype('uint8')*255),(1,1));ImageDraw.floodfill(pad,(0,0),127)
 bg=(np.array(pad)[1:-1,1:-1]==127)|((r>220)&(b>220)&(g<55))
 a[:,:,3]=np.asarray(Image.fromarray((~bg).astype('uint8')*255).filter(ImageFilter.MinFilter(3)))
 im=Image.fromarray(a);out=[]
 for y0,y1 in bands:
  top=max(0,y0-overlap);s=im.crop((0,top,im.width,min(im.height,y1+overlap)));aa=np.array(s.getchannel('A'));seen=np.zeros(aa.shape,bool)
  for sy,sx in zip(*np.where(aa>0)):
   if seen[sy,sx]:continue
   stack=[(sy,sx)];seen[sy,sx]=True;part=[]
   while stack:
    cy,cx=stack.pop();part.append((cy,cx))
    for ny,nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
     if 0<=ny<aa.shape[0] and 0<=nx<aa.shape[1] and aa[ny,nx] and not seen[ny,nx]:seen[ny,nx]=True;stack.append((ny,nx))
   cymean=sum(p[0] for p in part)/len(part)+top
   if len(part)<500 or not y0<=cymean<y1:
    for cy,cx in part:aa[cy,cx]=0
  s.putalpha(Image.fromarray(aa));s=s.crop(s.getbbox());out.append(s)
 return out

def cell(s,size,limit,left=None):
 scale=min(limit[0]/s.width,limit[1]/s.height)
 s=s.resize((round(s.width*scale),round(s.height*scale)),Image.Resampling.LANCZOS)
 s.putalpha(s.getchannel('A').point(lambda v:0 if v<24 else v))
 c=Image.new('RGBA',size);c.alpha_composite(s,((size[0]-s.width)//2 if left is None else left,(size[1]-s.height)//2));return c

def paint(raw,c,rect):
 im=decode(raw);im.paste(pack_color(c),rect[:2]);out=patch_bc3_rect(raw,im,rect)
 # Fully cleared source cells must decode without stray opaque background.
 al=np.array(unpack_color(decode(out)).crop(rect).getchannel('A'))
 intended=np.array(c.getchannel('A'))
 assert not np.any(al[intended==0]>0), 'Opaque background contamination'
 return out

if __name__=='__main__':
 sprites=keyed(V4/'menu_lettering_key.png',[(0,207),(207,397),(397,576),(576,765),(765,955)])
 extra=keyed(O/'additional_key.png',json.loads((O/'additional_bands.json').read_text()),32)
 sprites+=extra[:2]
 for i,s in enumerate(sprites+[extra[2]]):s.save(O/f'master_sprite_{i}.png')
 mode=(V4/'mode_select_v4.tex').read_bytes();proof=Image.new('RGBA',(1024,784))
 widths=[340,380,380,280,360,360,400]
 for i,s in enumerate(sprites):
  # Both states use the master aspect ratio, with only uniform downsampling.
  normal=cell(s,(512,112),(256,72),128)
  selected=cell(s,(widths[i],112),(min(320,widths[i]-12),92))
  full=Image.new('RGBA',(512,112));full.alpha_composite(selected)
  for x,c in [(0,full),(512,normal)]:
   rect=(x,i*112,x+512,(i+1)*112);mode=paint(mode,c,rect);proof.alpha_composite(c,rect[:2])
 (O/'mode_v5.tex').write_bytes(mode);preview(unpack_color(decode(mode)),O/'MODE_DECODED.png',(205,213,190,255))
 char=(V4/'charasele_v4.tex').read_bytes();rects=[(0,0,288,112),(0,120,288,240),(0,240,288,360),(0,360,288,480),(0,480,288,600)]
 for s,rect in zip(sprites,rects):char=paint(char,cell(s,(288,rect[3]-rect[1]),(276,88)),rect)
 (O/'char_v5.tex').write_bytes(char)
 lock=(O/'locked_source.tex').read_bytes();c=Image.new('RGBA',(1024,128));label=cell(extra[2],(640,128),(560,104));c.alpha_composite(label,(192,0));lock=paint(lock,c,(0,0,1024,128));(O/'lock_v5.tex').write_bytes(lock);preview(unpack_color(decode(lock)),O/'LOCKED_DECODED.png',(180,185,178,255))
 print('Built seven menu labels and both states, five submenu headings, and Locked; all cleared backgrounds decode transparent.')
