import sys,zipfile
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
from translations import TRANSLATIONS,RED_RECORDS
O=W.parent/'quest_v9';OUT=O/'release';ST=OUT/'root';ST.mkdir(parents=True,exist_ok=True)
def rows(raw):
 n=struct.unpack_from('>I',raw,12)[0];base=16+8*n
 return [list(struct.unpack_from('>'+str(ln)+'H',raw,base+2*off)) for off,ln in [struct.unpack_from('>II',raw,16+8*i) for i in range(n)]]
def rebuild(raw,rr):
 pool=[];tab=bytearray()
 for v in rr:tab+=struct.pack('>II',len(pool),len(v));pool+=v
 h=bytearray(raw[:16]);struct.pack_into('>I',h,8,len(pool));return bytes(h)+tab+struct.pack('>'+str(len(pool))+'H',*pool)
source=arc.parse_arc(ROM/'eng/tenka/smith.arc');original=arc.unpack(source.entries[25]);rr=rows(original);csa=arc.unpack(source.entries[24]);tnf=arc.unpack(source.entries[0]);mp={chr(i):struct.unpack_from('>H',csa,8+2*i)[0] for i in range(128)};widths={}
for i,text in TRANSLATIONS.items():
 controls=[v for v in rr[i] if v>=0xf000 and v not in [65534,65535]]
 assert controls==([65426,65425] if i in RED_RECORDS else []),(i,'Unexpected controls')
 vals=[]
 for ch in text:
  if ch=='\n':
   vals.append(65534)
   if i in RED_RECORDS:vals.extend([65426,2])
   continue
  assert ch in mp and mp[ch]!=65535,(i,ch)
  vals.append(mp[ch])
 rr[i]=vals+([65425] if i in RED_RECORDS else [])+[65535];widths[i]=max(sum(struct.unpack_from('>H',tnf,32+mp[ch]*8+6)[0] for ch in line) for line in text.split('\n'))
 assert widths[i]<=(190 if i<400 else 720),(i,widths[i])
new=rebuild(original,rr);assert rows(new)==rr
files=[]
with zipfile.ZipFile(OUT/'BACKUP_PRE_V9.zip','w',zipfile.ZIP_DEFLATED) as z:
 for rel in ['eng/tenka/smith.arc','eng/tenka/equip.arc','eng/result_id.arc']:
  p=ROM/rel;a=arc.parse_arc(p);reps={e.index:new for e in a.entries if e.name.endswith('id_brief_r') and arc.unpack(e)==original};assert reps
  path=p.relative_to(ROOT).as_posix();z.writestr(path,a.data);target=ST/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(arc.rebuild(a,reps));b=arc.parse_arc(target)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.flags,e.type_hash)==(f.name,f.flags,f.type_hash)
   if e.index in reps:
    assert rows(arc.unpack(f))==rr
    assert {i for i,(v,w) in enumerate(zip(rows(arc.unpack(e)),rr)) if v!=w}==set(TRANSLATIONS)
   else:assert e.compressed==f.compressed
  files.append(dict(path=path,source_sha256=arc.sha256(a.data),sha256=arc.sha256(target.read_bytes()),changes=[dict(index=i,name=a.entries[i].name) for i in reps],unchanged_resources=len(a.entries)-len(reps)))
r=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(x['changes']) for x in files),untouched_resources=sum(x['unchanged_resources'] for x in files),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2));(O/'TRANSLATIONS.json').write_text(json.dumps(TRANSLATIONS,indent=2));(O/'WIDTHS.json').write_text(json.dumps(widths,indent=2));print({k:v for k,v in r.items() if k!='files'})

