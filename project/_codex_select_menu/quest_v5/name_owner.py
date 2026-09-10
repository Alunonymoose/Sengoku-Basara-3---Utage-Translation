import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
a=arc.parse_arc(ROM/'eng/title_id.arc')
for e in a.entries:
 if 'cp_name' in e.name or e.index>=130:print(e.index,e.name)
a=arc.parse_arc(ROM/'eng/select/c_common.arc');ns=lsp_parse(arc.unpack(a.entries[75]))
for n in ns:
 if n['index'] in range(145,185):print(n['index'],n['name'],n['texture'],n['uv'])
