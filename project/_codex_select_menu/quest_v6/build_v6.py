import sys,json,struct,zipfile
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
V5=O;O=W.parent/'quest_v6'

def orange_sprites(path,bands):
 im=Image.open(path).convert('RGBA');a=np.array(im);r,g,b=[a[:,:,i].astype(int) for i in range(3)]
 # Orange is absent from every foreground colour in these masters.
 bg=(r>160)&(g>45)&(g<205)&(b<100)&(r>g+35)
 alpha=Image.fromarray((~bg).astype('uint8')*255).filter(ImageFilter.MinFilter(3));a[:,:,3]=np.array(alpha);a[np.array(alpha)==0,:3]=0;im=Image.fromarray(a)
 result=[]
 for y0,y1 in bands:
  top=max(0,y0-24);s=im.crop((0,top,im.width,min(im.height,y1+24)));aa=np.array(s.getchannel('A'));seen=np.zeros(aa.shape,bool)
  for sy,sx in zip(*np.where(aa>0)):
   if seen[sy,sx]:continue
   stack=[(sy,sx)];seen[sy,sx]=True;part=[]
   while stack:
    cy,cx=stack.pop();part.append((cy,cx))
    for ny,nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
     if 0<=ny<aa.shape[0] and 0<=nx<aa.shape[1] and aa[ny,nx] and not seen[ny,nx]:seen[ny,nx]=True;stack.append((ny,nx))
   mean=sum(p[0] for p in part)/len(part)+top
   if len(part)<450 or not y0<=mean<y1:
    for cy,cx in part:aa[cy,cx]=0
  s.putalpha(Image.fromarray(aa));result.append(s.crop(s.getbbox()))
 return result

if __name__=='__main__':
 quick=orange_sprites(O/'quick_key.png',[(0,Image.open(O/'quick_key.png').height)])[0];quick.save(O/'quick_sprite.png')
 opts=orange_sprites(O/'options_key.png',json.loads((O/'options_bands.json').read_text()))
 for i,s in enumerate(opts):s.save(O/f'option_sprite_{i}.png')
 title=arc.parse_arc(ROM/'eng/title.arc');mode=arc.unpack(title.entries[318]);cells=[]
 for x,size,limit,left in [(512,(512,112),(256,72),128),(0,(360,112),(320,92),None)]:
  c=cell(quick,size,limit,left);full=Image.new('RGBA',(512,112));full.alpha_composite(c);rect=(x,448,x+512,560);mode=paint(mode,full,rect);cells.append(('mode',rect,full))
 for x,limit,left in [(512,(340,56),128),(0,(400,74),30)]:
  c=cell(opts[4],(512,112),limit,left);rect=(x,784,x+512,896);mode=paint(mode,c,rect);cells.append(('mode',rect,c))
 (O/'mode_v6.tex').write_bytes(mode)
 raw=arc.unpack(arc.parse_arc(ROM/'eng/select/c_common.arc').entries[65]);rect=(0,480,288,600);c=cell(quick,(288,120),(276,88));raw=paint(raw,c,rect);(O/'char_v6.tex').write_bytes(raw);cells.append(('char',rect,c))
 options=arc.unpack(title.entries[319])
 for i,(s,selected_width,normal_left) in enumerate(zip(opts,[400,512,300,300],[40,60,88,88])):
  row=5+i
  for x,size,limit,left in [(512,(512,112),(380,52),normal_left),(0,(selected_width,112),(selected_width-24,70),None)]:
   c=cell(s,size,limit,left);full=Image.new('RGBA',(512,112));full.alpha_composite(c);rect=(x,row*112,x+512,(row+1)*112);options=paint(options,full,rect);cells.append(('options',rect,full))
 (O/'options_v6.tex').write_bytes(options)
 join=arc.unpack(title.entries[324]);phrase=unpack_color(decode(join)).crop((120,384,260,448));phrase=phrase.crop(phrase.getbbox())
 factor=min(152/phrase.width,44/phrase.height);phrase=phrase.resize((round(phrase.width*factor),round(phrase.height*factor)),Image.Resampling.LANCZOS)
 c=Image.new('RGBA',(512,64));c.alpha_composite(phrase,(24,(64-phrase.height)//2));join=paint(join,c,(0,384,512,448));(O/'join_v6.tex').write_bytes(join);cells.append(('join',(0,384,512,448),c))
 for i,(kind,rect,c) in enumerate(cells):c.save(O/f'cell_{i}.png')
 (O/'CELLS.json').write_text(json.dumps([dict(kind=k,rect=r,file=f'cell_{i}.png') for i,(k,r,c) in enumerate(cells)],indent=2))
 preview(unpack_color(decode(mode)),O/'MODE_PREVIEW.png',(206,212,195,255));preview(unpack_color(decode(options)),O/'OPTIONS_PREVIEW.png',(206,212,195,255));preview(unpack_color(decode(join)).crop((0,384,256,448)),O/'P2_NATIVE_SLOT.png',(120,42,42,255))
 print('Built bounded texture cells; decoded background opacity checks passed.')
