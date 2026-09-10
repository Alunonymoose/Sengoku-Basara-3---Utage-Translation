import sys,json,zipfile
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=Path(__file__).parent;OUT=O/'release';ST=OUT/'root';OUT.mkdir(exist_ok=True);ST.mkdir(exist_ok=True)
plan=defaultdict(dict)
# Only replace the bounded first-five mode cells, preserving every other label in each archive.
mode=(O/'mode_select_v4.tex').read_bytes();char=(O/'charasele_v4.tex').read_bytes();charrects=[tuple(x['rect']) for x in json.loads((O/'CHARASELE_BUILD.json').read_text())['cells']]
for r in json.loads((O/'ALL_MODE_OWNERS.json').read_text()):plan[Path(r['path'])][r['index']]=('mode',mode,[(0,0,1024,560)])
for r in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(r['path'])
 if 'og' in p.parts or 'backup' in p.name:continue
 if r['name'].endswith('charasele_00_000_ID_HQ'):plan[p][r['index']]=('charasele',char,charrects)
for r in json.loads((O/'BOOT_OWNERS.json').read_text()):
 if r['name'].endswith('common_009_ID_HQ'):plan[Path(r['path'])][r['index']]=('currency',(W/'currency_donor.tex').read_bytes(),[(200,0,256,64)])
backup=OUT/'BACKUP_PRE_V4.zip';reuse=backup.exists();files=[]
with zipfile.ZipFile(backup,'r' if reuse else 'w',zipfile.ZIP_DEFLATED) as bz:
 for p,jobs in sorted(plan.items()):
  assert p.is_relative_to(ROM/'eng') or p==ROM/'battleQuest.arc'
  assert not p.name.startswith('msg_') and p.name not in ['tenka_msg000.arc','tenka_msg001.arc']
  a=arc.parse_arc(p);reps={};changes=[]
  for idx,(kind,donor,rects) in jobs.items():
   raw=arc.unpack(a.entries[idx]);out=raw
   for rect in rects:out=transplant(out,donor,rect)
   if raw==out:continue
   reps[idx]=out;changes.append(dict(index=idx,name=a.entries[idx].name,kind=kind,rects=rects,before=arc.sha256(raw),after=arc.sha256(out)))
  if not reps:continue
  rel=p.relative_to(ROOT).as_posix()
  if reuse:assert bz.read(rel)==a.data,'Live source changed since backup'
  else:bz.writestr(rel,a.data)
  target=ST/rel;target.parent.mkdir(parents=True,exist_ok=True);rebuilt=arc.rebuild(a,reps);target.write_bytes(rebuilt)
  b=arc.parse_arc(target)
  assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.type_hash,e.flags,e.raw_size)==(f.name,f.type_hash,f.flags,f.raw_size)
   if e.index in reps:assert arc.unpack(f)==reps[e.index]
   else:assert e.compressed==f.compressed
  files.append(dict(path=rel,source_sha256=arc.sha256(a.data),sha256=arc.sha256(rebuilt),changes=changes,unchanged_resources=len(a.entries)-len(changes)))
report=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(x['changes']) for x in files),untouched_resources=sum(x['unchanged_resources'] for x in files),backup=str(backup),backup_sha256=arc.sha256(backup.read_bytes()),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
