import sys,json
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5'
for p in (ROM/'eng').glob('*.arc'):
 a=arc.parse_arc(p)
 for e in a.entries:
  if any(t in e.name for t in ['qqq','999','mik']) and 'texture' in e.name:
   print(p.name,e.index,e.name)
   if 'charasele' in e.name:preview(unpack_color(decode(arc.unpack(e))),O/(p.stem+'_'+str(e.index)+'_locked.png'))
a=arc.parse_arc(ROM/'eng/title.arc');ns=lsp_parse(arc.unpack(a.entries[341]))
for n in ns:
 if n['index'] in [24,72,153,154,155,156,157]:print(json.dumps(n))
