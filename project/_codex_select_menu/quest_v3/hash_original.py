from common import *
for r in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(r['path'])
 if 'og' in p.parts or 'backup' in p.name or not r['name'].endswith('charasele_00_000_ID_HQ'):continue
 j=ROM/'jpn'/p.relative_to(ROM/'eng')
 if j.exists():
  a=arc.parse_arc(j);e=next(e for e in a.entries if e.name==r['name']);raw=arc.unpack(e);print(str(j.relative_to(ROM)),arc.sha256(raw))
