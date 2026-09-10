import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v7';O.mkdir(exist_ok=True)
for rel in ['eng/tenka/smith.arc','eng/tenka/tenka.arc','eng/tenka/tenka_pl016.arc','eng/tenka/equip.arc']:
 p=ROM/rel
 if not p.exists():continue
 a=arc.parse_arc(p)
 for e in a.entries:
  print(rel,e.index,e.name,hex(e.type_hash))
  if e.type_hash==0x60DD1B16:
   (O/(p.stem+'_'+str(e.index)+'_nodes.json')).write_text(json.dumps(lsp_parse(arc.unpack(e)),indent=2))
  elif 'texture' in e.name and any(x in e.name for x in ['tenka_','shop','common_','name']):
   try:preview(unpack_color(decode(arc.unpack(e))),O/(p.stem+'_'+str(e.index)+'.png'))
   except Exception as ex:print('decode',ex)

