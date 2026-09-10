import sys,json
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5';nodes=[]
for p in (ROM/'eng/select').glob('*.arc'):
 a=arc.parse_arc(p)
 for e in a.entries:
  if e.type_hash==0x60DD1B16:
   try:ns=lsp_parse(arc.unpack(e))
   except:continue
   for n in ns:
    if any(s in n['name'].lower() for s in ['lock','mikai','join','start','2p','p2','kaiho']):nodes.append(dict(arc=str(p),lsp_index=e.index,lsp=e.name,**n))
  if p.name=='c_common.arc' and any(s in e.name for s in ['charasele_00_00','common_00']):
   raw=arc.unpack(e)
   if raw[:4]==b'\0XET':preview(unpack_color(decode(raw)),O/f'common_{e.index}.png');print(e.index,e.name,xet_info(raw)['width'],xet_info(raw)['height'])
(O/'SUBMENU_NODES.json').write_text(json.dumps(nodes,indent=2))
print(json.dumps(nodes,indent=2))
