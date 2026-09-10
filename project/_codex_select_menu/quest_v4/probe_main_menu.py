import sys
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v4'
for p in [ROM/'eng/title.arc',ROM/'eng/title_id.arc',*(ROM/'eng/title').glob('*.arc')]:
 a=arc.parse_arc(p)
 print('\nARC',p)
 for e in a.entries:
  if e.type_hash==0x60DD1B16:
   try:
    ns=lsp_parse(arc.unpack(e));(O/(p.stem+'_'+str(e.index)+'_nodes.json')).write_text(json.dumps(ns,indent=2));print('LSP',e.index,e.name)
   except Exception as ex: print(ex)
  elif 'texture' in e.name and any(s in e.name for s in ['top_','title','common_009']):
   r=arc.unpack(e)
   if r[:4]==b'\0XET':
    inf=xet_info(r);print(e.index,e.name,inf['width'],inf['height']);preview(unpack_color(decode(r)),O/(p.stem+'_'+str(e.index)+'.png'))
