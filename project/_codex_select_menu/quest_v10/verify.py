import json,zipfile,sys
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
O=W.parent/'quest_v10';OUT=O/'release';r=json.loads((OUT/'VALIDATION.json').read_text());assert r['translated_records']==198
with zipfile.ZipFile(OUT/'BACKUP_PRE_V10.zip') as z:
 assert z.testzip() is None
 for rec in r['files']:
  p=OUT/'root'/rec['path']; assert arc.sha256(p.read_bytes())==rec['sha256']; src=z.read(rec['path']); assert arc.sha256(src)==rec['source_sha256']
  Path(OUT/'before.arc').write_bytes(src); a=arc.parse_arc(Path(OUT/'before.arc')); b=arc.parse_arc(p); assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert (e.name,e.type_hash,e.flags)==(f.name,f.type_hash,f.flags)
   if e.index not in {x['index'] for x in rec['changes']}: assert e.compressed==f.compressed
assert all(v<=720 for v in json.loads((O/'WIDTHS.json').read_text()).values())
out={'status':'pass','archives':r['archives'],'changed_resources':r['changed_resources'],'translated_records':198,'untouched_resources':r['untouched_resources'],'checks':['Archive hashes and CRC','Unchanged compressed entries identical','Resource metadata preserved','198 records and width limits'],'runtime_verified':False}
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(out,indent=2));print(out)

