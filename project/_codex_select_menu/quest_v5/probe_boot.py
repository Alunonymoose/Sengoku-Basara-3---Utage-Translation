import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5'
for p in [ROM/'eng/init_ps3.arc',ROM/'eng/title.arc']:
 a=arc.parse_arc(p)
 for e in a.entries:
  if 'common' in e.name and ('texture' in e.name or 'lsp' in e.name):
   print(p.name,e.index,e.name)
   if e.type_hash==0x60DD1B16:
    ns=lsp_parse(arc.unpack(e));(O/(p.stem+'_common_nodes.json')).write_text(json.dumps(ns,indent=2))
   elif any(z in e.name for z in ['common_000','common_001','common_002','common_003','common_004','common_005','common_006','common_007']):preview(unpack_color(decode(arc.unpack(e))),O/(p.stem+'_'+str(e.index)+'.png'))
print('Shared select folders:',[str(p) for p in ROM.glob('*select*')])
