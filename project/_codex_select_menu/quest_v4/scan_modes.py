import sys,struct,json
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v4';rows=[]
for p in (ROM/'eng').rglob('*.arc'):
 if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc'] or any(x in ['demo','og','backup'] for x in p.parts) or 'backup' in p.name.lower():continue
 with p.open('rb') as f:
  h=f.read(8)
  if h[:4]!=b'\0CRA':continue
  n=struct.unpack_from('>H',h,6)[0];tb=f.read(n*80)
 for i in range(n):
  name=tb[i*80:i*80+64].split(b'\0')[0].decode('latin1')
  if name.endswith('mode_select_000_ID_HQ'):rows.append(dict(path=str(p),index=i,name=name))
(O/'ALL_MODE_OWNERS.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
