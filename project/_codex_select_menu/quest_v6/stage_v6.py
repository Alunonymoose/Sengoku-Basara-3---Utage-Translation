from build_v6 import *
OUT=O/'release';ST=OUT/'root';ST.mkdir(parents=True,exist_ok=True);plan=defaultdict(dict)
def job(p,i,k,rects):plan[Path(p)][i]=(k,(O/f'{k}_v6.tex').read_bytes(),rects)
for r in json.loads((V4/'ALL_MODE_OWNERS.json').read_text()):job(r['path'],r['index'],'mode',[(0,448,1024,560),(0,784,1024,896)])
for r in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(r['path'])
 if 'og' in p.parts or 'backup' in p.name:continue
 if r['name'].endswith('charasele_00_000_ID_HQ'):job(p,r['index'],'char',[(0,480,288,600)])
for r in json.loads((O/'OWNERS.json').read_text()):
 if r['name'].endswith('mode_select_003_ID_HQ'):job(r['path'],r['index'],'options',[(0,560,1024,1008)])
 else:job(r['path'],r['index'],'join',[(0,384,512,448)])
for r in json.loads((V5/'OWNERS_V5.json').read_text()):
 if 'lsp' in r['name']:plan[Path(r['path'])][r['index']]=('mode_layout' if 'mode_select' in r['name'] else 'join_layout',None,[])

def layout(raw,kind):
 out=bytearray(raw);edits=[]
 for n in lsp_parse(raw):
  base=16+n['index']*176
  def change(off,fmt,value):
   at=base+off;before=bytes(out[at:at+4]);after=struct.pack('>'+fmt,value)
   if before!=after:out[at:at+4]=after;edits.append(dict(node=n['index'],name=n['name'],offset=at,before=before.hex(),after=after.hex()))
  if kind=='mode_layout' and n['name'] in ['KANKYO_shadow','CONTROLLER_shadow','SAVE_shadow','LOAD_shadow','DOUKI_shadow']:
   assert n['position'] in [[2.,2.],[4.,5.]],n
   change(0,'f',1.);change(4,'f',1.5)
  if kind=='join_layout' and n['name'] in ['2P_IN','2P_IN2']:
   assert n['uv']==[60,192,130,224] and n['geometry']==[0,-16,70,16] and n['position']==[22.,0.],n
   change(0,'f',12.);change(0x7c,'i',128);change(0x84,'i',0);change(0x8c,'i',128)
 assert len(edits)==(10 if kind=='mode_layout' else 8),(kind,len(edits))
 return bytes(out),edits

backup=OUT/'BACKUP_PRE_V6.zip';reuse=backup.exists();files=[]
with zipfile.ZipFile(backup,'r' if reuse else 'w',zipfile.ZIP_DEFLATED) as bz:
 for p,jobs in sorted(plan.items()):
  assert p.is_relative_to(ROM/'eng') or p==ROM/'battleQuest.arc'
  assert not p.name.startswith('msg_') and p.name not in ['tenka_msg000.arc','tenka_msg001.arc']
  a=arc.parse_arc(p);reps={};changes=[]
  for idx,(kind,donor,rects) in jobs.items():
   raw=arc.unpack(a.entries[idx]);out=raw;edits=[]
   if kind.endswith('layout'):out,edits=layout(raw,kind)
   else:
    for rect in rects:out=transplant(out,donor,rect)
   if raw==out:continue
   reps[idx]=out;changes.append(dict(index=idx,name=a.entries[idx].name,kind=kind,rects=rects,edits=edits,before=arc.sha256(raw),after=arc.sha256(out)))
  if not reps:continue
  rel=p.relative_to(ROOT).as_posix()
  if reuse:assert bz.read(rel)==a.data,'Live file changed since backup'
  else:bz.writestr(rel,a.data)
  target=ST/rel;target.parent.mkdir(parents=True,exist_ok=True);rebuilt=arc.rebuild(a,reps);target.write_bytes(rebuilt);b=arc.parse_arc(target)
  assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.type_hash,e.flags,e.raw_size)==(f.name,f.type_hash,f.flags,f.raw_size)
   if e.index in reps:assert arc.unpack(f)==reps[e.index]
   else:assert e.compressed==f.compressed
  files.append(dict(path=rel,source_sha256=arc.sha256(a.data),sha256=arc.sha256(rebuilt),changes=changes,unchanged_resources=len(a.entries)-len(changes)))
r=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(x['changes']) for x in files),untouched_resources=sum(x['unchanged_resources'] for x in files),backup=str(backup),backup_sha256=arc.sha256(backup.read_bytes()),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
