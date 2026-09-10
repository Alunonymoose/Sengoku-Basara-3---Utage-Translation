import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
a=arc.parse_arc(ROM/'eng/select/c_common.arc')
for e in a.entries:print(e.index,e.name)
# Print only compact candidates around the lock nodes, plus bottom control names.
ns=lsp_parse(arc.unpack(a.entries[75]))
for n in ns:
 if n['index']>=360:print(n['index'],n['name'],n['texture'],n['uv'])
