from common import *
from collections import defaultdict
import zipfile
OUT=W/'release';STAGE=OUT/'root';OUT.mkdir(exist_ok=True);STAGE.mkdir(exist_ok=True)
plans=defaultdict(dict)
for rec in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(rec['path'])
 if 'og' in p.parts or 'backup' in p.name:continue
 if rec['name'].endswith('charasele_00_000_ID_HQ'):plans[p][rec['index']]=W/'charasele_v3.tex'
# Quest texture duplicate in the briefing screen is synchronized as well.
for rec in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(rec['path'])
 if 'og' not in p.parts and rec['name'].endswith('yuugi_quest_002_ID_HQ'):plans[p][rec['index']]=W/'quest002_v3.tex'
old=json.loads((V2/'rewards/REWARD_CANDIDATES.json').read_text())
for rec in old['resource_replacements']:plans[Path(rec['arc'])][rec['index']]=W/'names'/(rec['key']+'.tex')
# Resolve all sources from current live files; a changed archive will fail the later install guard.
records=[];allchanges=[]
backup=OUT/'BACKUP_PRE_V3.zip';assert not backup.exists(),'Do not replace an existing rollback backup'
with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as bz:
 for p,reps in sorted(plans.items()):
  assert p.is_relative_to(ROM/'eng') and not p.name.startswith('msg_') and p.name not in ['tenka_msg000.arc','tenka_msg001.arc']
  a=arc.parse_arc(p);replacement={i:f.read_bytes() for i,f in reps.items()}
  # Official English Z, only the native currency cell; preserve every numeral.
  for e in a.entries:
   if e.name.endswith('common_009_ID_HQ'):
    replacement[e.index]=transplant(arc.unpack(e),(W/'currency_donor.tex').read_bytes(),(200,0,256,64))
  rel=p.relative_to(ROOT);target=STAGE/rel;target.parent.mkdir(parents=True,exist_ok=True)
  bz.writestr(str(rel).replace('\\','/'),a.data);new=arc.rebuild(a,replacement);target.write_bytes(new)
  b=arc.parse_arc(target);assert len(a.entries)==len(b.entries)
  local=[]
  for e,f in zip(a.entries,b.entries):
   assert (e.name,e.type_hash,e.flags,e.raw_size)==(f.name,f.type_hash,f.flags,f.raw_size)
   if e.index in replacement:
    assert arc.unpack(f)==replacement[e.index]
    r0,r1=arc.unpack(e),arc.unpack(f);assert r0[:20]==r1[:20] and len(r0)==len(r1)
    local.append(dict(index=e.index,name=e.name,before=arc.sha256(r0),after=arc.sha256(r1)))
   else:assert e.compressed==f.compressed
  records.append(dict(path=str(rel).replace('\\','/'),source_sha256=arc.sha256(a.data),sha256=arc.sha256(new),changes=local,unchanged_resources=len(a.entries)-len(local)))
report=dict(status='staged',files=records,archives=len(records),changed_resources=sum(len(r['changes']) for r in records),untouched_resources=sum(r['unchanged_resources'] for r in records),backup=str(backup),backup_sha256=arc.sha256(backup.read_bytes()),lsp_unchanged=True,runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
