from common import *
from PIL import ImageDraw
p=ROM/'eng/quest/menu.arc';a=arc.parse_arc(p);j=arc.parse_arc(ROM/'jpn/quest/menu.arc');raw=arc.unpack(a.entries[30]);orig=arc.unpack(j.entries[30]);im=unpack_color(decode(raw));out=transplant(raw,orig,(0,192,464,256))
# Refit old English stamp art to its own native UV slots; keep it out of the reward row.
im=Image.open(W/'stamp_master.png').convert('RGBA')
jobs=[('CLEAR',[(176,237),(584,176),(664,745),(256,804)],(296,256,376,360)),('GET',[(888,235),(1296,176),(1376,745),(970,804)],(376,256,512,440))]
for label,poly,rect in jobs:
 mask=Image.new('L',im.size);ImageDraw.Draw(mask).polygon(poly,fill=255)
 import PIL.ImageChops as IC
 sprite=im.copy();sprite.putalpha(IC.multiply(sprite.getchannel('A'),mask));bb=sprite.getchannel('A').getbbox();sprite=sprite.crop(bb);w,h=rect[2]-rect[0],rect[3]-rect[1];sc=min((w-8)/sprite.width,(h-8)/sprite.height);sprite=sprite.resize((round(sprite.width*sc),round(sprite.height*sc)),Image.Resampling.LANCZOS)
 cell=Image.new('RGBA',(w,h));cell.alpha_composite(sprite,((w-sprite.width)//2,(h-sprite.height)//2));packed=decode(out);packed.paste(pack_color(cell),rect[:2]);out=patch_bc3_rect(out,packed,rect)
# Clean former stamp overhang in unused regions, without touching labels.
for rect in [(464,192,512,256),(296,360,376,400),(328,400,376,440),(216,304,296,352)]:out=transplant(out,orig,rect)
(W/'quest002_v3.tex').write_bytes(out);preview(unpack_color(decode(out)),W/'QUEST_ATLAS_V3_PREVIEW.png')
# Look up an actual official English currency sprite, preserving numeric slots.
SH=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng')
for p in [*SH.glob('*.arc'),*(SH/'tenka').glob('*.arc')]:
 a=arc.parse_arc(p)
 for e in a.entries:
  if e.name.endswith('common_009_ID_HQ'):
   r=arc.unpack(e);(W/'currency_donor.tex').write_bytes(r);preview(unpack_color(decode(r)),W/'CURRENCY_DONOR.png');print('Currency donor',p,e.index);raise SystemExit
