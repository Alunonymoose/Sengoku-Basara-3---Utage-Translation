import sys,struct,json
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=W.parent/'quest_v5';found=[]
for p in [*(ROM/'eng').rglob('*.arc'),*ROM.glob('*.arc')]:
 if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc'] or any(x in ['demo','og','backup'] for x in p.parts) or 'backup' in p.name.lower():continue
 with p.open('rb') as f:
  h=f.read(8)
  if h[:4]!=b'\0CRA':continue
  n=struct.unpack_from('>H',h,6)[0];tb=f.read(n*80)
 for i in range(n):
  name=tb[i*80:i*80+64].split(b'\0')[0].decode('latin1')
  if name.endswith(('charasele_02_lock_ID_HQ','lsp\\jpn\\common\\common_00','lsp\\jpn\\mode_select\\mode_select')):found.append(dict(path=str(p),index=i,name=name))
(O/'OWNERS_V5.json').write_text(json.dumps(found,indent=2));print(json.dumps(found,indent=2))
a=arc.parse_arc(ROM/'eng/title_id.arc');raw=arc.unpack(a.entries[141]);(O/'locked_source.tex').write_bytes(raw);preview(unpack_color(decode(raw)),O/'LOCKED_SOURCE.png');print('locked dimensions',xet_info(raw))
