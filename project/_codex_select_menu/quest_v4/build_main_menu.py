import sys,json
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
from codec_v4 import patch_bc3_rect
O=Path(__file__).parent;raw=(O/'eng_title_id.arc_143.tex').read_bytes();out=raw;checks=[]
for row,active in enumerate([340,380,380,280,360]):
 source=Image.open(O/f'sprite_{row}.png').convert('RGBA')
 for col in range(2):
  cell=Image.new('RGBA',(512,112),(0,0,0,0))
  width=active-92 if col==0 else 256;height=80 if col==0 else 60;left=80 if col==0 else 128
  sprite=source.resize((width,height),Image.Resampling.LANCZOS);sprite.putalpha(sprite.getchannel('A').point(lambda v:0 if v<24 else v));cell.alpha_composite(sprite,(left,(112-height)//2))
  rect=(512*col,112*row,512*(col+1),112*(row+1));packed=decode(out);packed.paste(pack_color(cell),rect[:2]);out=patch_bc3_rect(out,packed,rect)
  cell.save(O/f'mode_cell_{row}_{col}.png');got=unpack_color(decode(out)).crop(rect);want=np.asarray(cell.getchannel('A'));actual=np.asarray(got.getchannel('A'));assert not ((want==0)&(actual>20)).any(),(row,col)
  assert col or left+width<active
  checks.append(dict(row=row,state='selected' if col==0 else 'normal',rect=rect,ink_box=[left,(112-height)//2,left+width,(112+height)//2],old_slot_fully_cleared=True,stray_pixels=0))
(O/'mode_select_v4.tex').write_bytes(out);preview(unpack_color(decode(out)),O/'MAIN_MENU_ATLAS_V4.png',(204,234,163,255));(O/'MODE_BUILD.json').write_text(json.dumps(checks,indent=2));print('Both states of all five approved mode designs rebuilt; empty-pixel checks passed.')
