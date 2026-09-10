import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5';a=arc.parse_arc(ROM/'eng/select/c_common.arc')
for i in [68,69,70,71,73,74]:preview(unpack_color(decode(arc.unpack(a.entries[i]))),O/f'common_{i}.png')
ns=lsp_parse(arc.unpack(a.entries[75]))
for n in ns:
 if any(t in n['texture'] for t in ['common_010','common_014','common_015','common_016','charasele_02_qqq']):print(n['index'],n['name'],n['texture'].split('\\')[-1],n['uv'])
