from build_v5 import *
OUT=O/'release';ST=OUT/'root';ST.mkdir(parents=True,exist_ok=True)
plan=defaultdict(dict)
for r in json.loads((V4/'ALL_MODE_OWNERS.json').read_text()):plan[Path(r['path'])][r['index']]=('mode',(O/'mode_v5.tex').read_bytes(),[(0,0,1024,784)])
for r in json.loads((W/'ATLAS_OWNERS.json').read_text()):
 p=Path(r['path'])
 if 'og' in p.parts or 'backup' in p.name:continue
 if r['name'].endswith('charasele_00_000_ID_HQ'):plan[p][r['index']]=('charasele',(O/'char_v5.tex').read_bytes(),[(0,0,288,112),(0,120,288,240),(0,240,288,360),(0,360,288,480),(0,480,288,600)])
for r in json.loads((O/'OWNERS_V5.json').read_text()):
 kind='locked' if 'texture' in r['name'] else ('mode_layout' if 'mode_select' in r['name'] else 'join_layout')
 plan[Path(r['path'])][r['index']]=(kind,(O/'lock_v5.tex').read_bytes() if kind=='locked' else None,[(0,0,1024,128)] if kind=='locked' else [])
 if kind=='join_layout':
  source=arc.parse_arc(ROM/'eng/title.arc');donor=arc.unpack(source.entries[324])
  local=arc.parse_arc(Path(r['path']))
  for e in local.entries:
   if e.name.endswith('common_000_ID_HQ'):plan[Path(r['path'])][e.index]=('join_text',donor,[(0,384,512,448)])

def layout(raw,kind):
 out=bytearray(raw);edits=[]
 for n in lsp_parse(raw):
  base=16+n['index']*176
  def change(off,fmt,value):
   at=base+off;before=bytes(out[at:at+4]);after=struct.pack('>'+fmt,value)
   if before!=after:out[at:at+4]=after;edits.append(dict(node=n['index'],name=n['name'],offset=at,before=before.hex(),after=after.hex()))
  if kind=='mode_layout' and n['index'] in [19,21,23,25,27,29,31]:
   assert n['position']==[4.,5.] and 'mode_select_000' in n['texture'],n
   change(0,'f',1.0);change(4,'f',1.5)
  if kind=='join_layout' and n['name'] in ['2P_IN','2P_IN2']:
   assert n['uv']==[0,192,128,224] and n['geometry']==[0,-16,128,16] and n['position']==[12.,0.],n
   change(0,'f',22.);change(0x7c,'i',70);change(0x84,'i',60);change(0x8c,'i',130)
 assert len(edits)==(14 if kind=='mode_layout' else 8), (kind,len(edits))
 return bytes(out),edits

backup=OUT/'BACKUP_PRE_V5.zip';reuse=backup.exists()
files=[]
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
  if reuse:assert bz.read(rel)==a.data,'Live archive changed since backup'
  else:bz.writestr(rel,a.data)
  target=ST/rel;target.parent.mkdir(parents=True,exist_ok=True);rebuilt=arc.rebuild(a,reps);target.write_bytes(rebuilt)
  b=arc.parse_arc(target);assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.type_hash,e.flags,e.raw_size)==(f.name,f.type_hash,f.flags,f.raw_size)
   if e.index in reps:assert arc.unpack(f)==reps[e.index]
   else:assert e.compressed==f.compressed
  files.append(dict(path=rel,source_sha256=arc.sha256(a.data),sha256=arc.sha256(rebuilt),changes=changes,unchanged_resources=len(a.entries)-len(changes)))
r=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(x['changes']) for x in files),untouched_resources=sum(x['unchanged_resources'] for x in files),backup=str(backup),backup_sha256=arc.sha256(backup.read_bytes()),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
