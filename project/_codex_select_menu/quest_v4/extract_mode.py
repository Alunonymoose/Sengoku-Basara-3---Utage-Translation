import sys
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v4'
for sub in ['eng','jpn']:
 for name in ['title.arc','title_id.arc']:
  a=arc.parse_arc(ROM/sub/name)
  for e in a.entries:
   if e.name.endswith('mode_select_000_ID_HQ'):
    r=arc.unpack(e);(O/f'{sub}_{name}_{e.index}.tex').write_bytes(r);preview(unpack_color(decode(r)),O/f'{sub}_{name}_{e.index}.png');print(sub,name,e.index,xet_info(r))
