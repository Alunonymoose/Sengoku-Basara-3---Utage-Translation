exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
from PIL import ImageDraw
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');a=arc.parse_arc(ROM/'eng/tenka/smith.arc');tnf=arc.unpack(a.entries[0]);pages={int(e.name.split('_')[-3]):unpack_color(decode(arc.unpack(e))) for e in a.entries if e.name.startswith('msg\\') and e.name.endswith('_ID_HQ')};rs=json.loads((O/'shop_25.json').read_text())
def render(vals):
 out=Image.new('RGBA',(1800,128));x=y=0;i=0
 while i<len(vals):
  v=vals[i];i+=1
  if v>=0xf000:
   if v==65534:y+=54;x=0
   elif v in [65426,65425]:i+=1
   continue
  if v>=struct.unpack_from('>I',tnf,8)[0]:continue
  gid,u,w,adv=struct.unpack_from('>4H',tnf,32+v*8);im=pages[gid>>8].crop((u*2,w*2,u*2+adv*2,w*2+52))
  if x+im.width>1800:y+=54;x=0
  if y+52>128:break
  out.alpha_composite(im,(x,y));x+=adv*2
 return out
for start in [500,520,540]:
 sheet=Image.new('RGBA',(1900,20*132),(32,32,32,255));draw=ImageDraw.Draw(sheet)
 for k in range(20):draw.text((5,k*132+12),str(start+k),fill='white');sheet.alpha_composite(render(rs[start+k]['values']),(60,k*132))
 sheet.convert('RGB').save(O/f'RECORDS_{start}.png')
