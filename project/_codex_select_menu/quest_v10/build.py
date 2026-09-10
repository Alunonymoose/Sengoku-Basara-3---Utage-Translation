import sys,re,zipfile
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
from translations import TRANSLATIONS
from font_support import extend_font
O=W.parent/'quest_v10';OUT=O/'release';ST=OUT/'root';ST.mkdir(parents=True,exist_ok=True)
assert not (OUT/'INSTALL_RESULT.json').exists(),'Already installed; preserve backup'
def rows(raw):
 n=struct.unpack_from('>I',raw,12)[0];base=16+8*n
 return [list(struct.unpack_from('>'+str(ln)+'H',raw,base+2*off)) for off,ln in [struct.unpack_from('>II',raw,16+8*i) for i in range(n)]]
def rebuild(raw,rr):
 pool=[];tab=bytearray()
 for v in rr:tab+=struct.pack('>II',len(pool),len(v));pool+=v
 h=bytearray(raw[:16]);struct.pack_into('>I',h,8,len(pool));return bytes(h)+tab+struct.pack('>'+str(len(pool))+'H',*pool)
source=arc.parse_arc(ROM/'eng/tenka/smith.arc');original=arc.unpack(source.entries[25]);rr=rows(original);fontmap=extend_font(source);csa=fontmap[arc.unpack(source.entries[24])];tnf=fontmap[arc.unpack(source.entries[0])];mp={chr(i):struct.unpack_from('>H',csa,8+2*i)[0] for i in range(128)};widths={}
def control_stream(v):
 out=[];i=0
 while i<len(v):
  x=v[i];i+=1
  if x in [65534,65535]:continue
  if x==65426:out.extend([x,v[i]]);i+=1
  elif x>=0xf000:out.append(x)
 return out
for idx,text in TRANSLATIONS.items():
 if idx>=400:
  wrapped=[]
  for line in text.split('\n'):
   current=''
   for word in line.split(' '):
    candidate=(current+' '+word).strip();plain=candidate.replace('<c>','').replace('</c>','')
    width=sum(struct.unpack_from('>H',tnf,32+mp[ch]*8+6)[0] for ch in plain if ch in mp and mp[ch]!=65535)
    if width>720 and current:wrapped.append(current);current=word
    else:current=candidate
   wrapped.append(current)
  assert len(wrapped)<=2,(idx,'Needs shorter text',wrapped)
  text='\n'.join(wrapped);TRANSLATIONS[idx]=text
 old=rr[idx];ct=control_stream(old);color=ct[1] if ct else None
 assert ct in [[],[65426,2,65425],[65426,4,65425]],(idx,ct)
 vals=[]
 for part in re.split('(<c>|</c>)',text):
  if part=='<c>':assert color is not None;vals.extend([65426,color]);continue
  if part=='</c>':vals.append(65425);continue
  for ch in part:
   if ch=='\n':vals.append(65534);continue
   assert ch in mp and mp[ch]!=65535,(idx,ch)
   vals.append(mp[ch])
 vals.append(65535);assert control_stream(vals)==ct,(idx,ct,control_stream(vals));rr[idx]=vals
 plain=text.replace('<c>','').replace('</c>','');widths[idx]=max(sum(struct.unpack_from('>H',tnf,32+mp[ch]*8+6)[0] for ch in line) for line in plain.split('\n'))
 assert widths[idx]<=(190 if idx<400 else 720),(idx,widths[idx],plain)
new=rebuild(original,rr);assert rows(new)==rr
files=[]
with zipfile.ZipFile(OUT/'BACKUP_PRE_V10.zip','w',zipfile.ZIP_DEFLATED) as z:
 for rel in ['eng/tenka/smith.arc','eng/tenka/equip.arc','eng/result_id.arc']:
  p=ROM/rel;a=arc.parse_arc(p);reps={};kinds={}
  for e in a.entries:
   raw=arc.unpack(e)
   if e.name.endswith('id_brief_r') and raw==original:reps[e.index]=new;kinds[e.index]='text'
   elif e.name.startswith('msg\\id_brief\\') and raw in fontmap:reps[e.index]=fontmap[raw];kinds[e.index]='font'
  assert len(reps)==(8 if rel=='eng/result_id.arc' else 4),(rel,len(reps))
  path=p.relative_to(ROOT).as_posix();z.writestr(path,a.data);target=ST/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(arc.rebuild(a,reps));b=arc.parse_arc(target)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.flags,e.type_hash)==(f.name,f.flags,f.type_hash)
   if e.index in reps:assert arc.unpack(f)==reps[e.index]
   else:assert e.compressed==f.compressed
  files.append(dict(path=path,source_sha256=arc.sha256(a.data),sha256=arc.sha256(target.read_bytes()),changes=[dict(index=i,name=a.entries[i].name,kind=kinds[i]) for i in reps],unchanged_resources=len(a.entries)-len(reps)))
r=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(x['changes']) for x in files),untouched_resources=sum(x['unchanged_resources'] for x in files),translated_records=len(TRANSLATIONS),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2));(O/'TRANSLATIONS.json').write_text(json.dumps(TRANSLATIONS,indent=2));(O/'WIDTHS.json').write_text(json.dumps(widths,indent=2));print({k:v for k,v in r.items() if k!='files'})
