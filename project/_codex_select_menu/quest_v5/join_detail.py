import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5';a=arc.parse_arc(ROM/'eng/title.arc');im=unpack_color(decode(arc.unpack(a.entries[324])));im.crop((100,384,410,448)).resize((930,192)).save(O/'join_detail.png');preview(unpack_color(decode(arc.unpack(a.entries[328]))),O/'common023.png')
