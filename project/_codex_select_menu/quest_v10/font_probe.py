import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
a=arc.parse_arc(Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\tenka\smith.arc'))
for e in a.entries[:15]:
 raw=arc.unpack(e);print(e.index,e.name,len(raw),raw[:32].hex())
