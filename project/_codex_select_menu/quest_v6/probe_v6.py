import sys,struct,json
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v6'
Image.open(W.parent/'quest_v4/menu_lettering_key.png').crop((0,765,1024,955)).save(O/'quick_source.png')
for rel in ['eng/pause/option.arc','eng/title.arc','eng/title_id.arc']:
 a=arc.parse_arc(ROM/rel)
 for e in a.entries:
  if 'option' in e.name or ('mode_select' in e.name and e.type_hash==0x60DD1B16):
   raw=arc.unpack(e);print(rel,e.index,e.name)
   if e.type_hash==0x60DD1B16:(O/(Path(rel).stem+'_'+str(e.index)+'_nodes.json')).write_text(json.dumps(lsp_parse(raw),indent=2))
   elif 'texture' in e.name:preview(unpack_color(decode(raw)),O/(Path(rel).stem+'_'+str(e.index)+'.png'))
