import sys,zipfile
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
O=W.parent/'quest_v7';OUT=O/'release';report=json.loads((OUT/'VALIDATION.json').read_text());tmp=OUT/'audit';tmp.mkdir(exist_ok=True)
def records(raw):
 n=struct.unpack_from('>I',raw,12)[0];base=16+8*n
 return [list(struct.unpack_from('>'+str(ln)+'H',raw,base+2*off)) for off,ln in [struct.unpack_from('>II',raw,16+i*8) for i in range(n)]]
def texture_check(a,b,rects):
 assert a[:20]==b[:20] and len(a)==len(b)
 width,height=decode(a).size;changed=np.frombuffer(a[20:],dtype=np.uint8).reshape(-1,16)!=np.frombuffer(b[20:],dtype=np.uint8).reshape(-1,16)
 allow=np.zeros((height//4,width//4),bool)
 for x,y,x1,y1 in rects:allow[y//4:y1//4,x//4:x1//4]=True
 assert not np.any(changed.any(1)&~allow.ravel())
oldrows=None;newrows=None;count=0
with zipfile.ZipFile(OUT/'BACKUP_PRE_V7.zip') as z:
 assert z.testzip() is None
 for rec in report['files']:
  before=z.read(rec['path']);assert arc.sha256(before)==rec['source_sha256'];p=tmp/'before.arc';p.write_bytes(before);a=arc.parse_arc(p)
  p=OUT/'root'/rec['path'];assert arc.sha256(p.read_bytes())==rec['sha256'];b=arc.parse_arc(p);changes={x['index']:x for x in rec['changes']};assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.flags,e.type_hash)==(f.name,f.flags,f.type_hash)
   if e.index not in changes:assert e.compressed==f.compressed;continue
   before=arc.unpack(e);after=arc.unpack(f);assert before!=after;count+=1;kind=changes[e.index]['kind']
   if kind=='shop text':
    oldrows=records(before);newrows=records(after);assert len(oldrows)==len(newrows)==1963
    assert {i for i,(x,y) in enumerate(zip(oldrows,newrows)) if x!=y}==set(range(332,336))|set(range(532,544))
    assert all(newrows[i][-1]==65535 for i in set(range(332,336))|set(range(532,544)))
   elif kind=='character name':texture_check(before,after,[(0,0,256,128)]);al=np.array(unpack_color(decode(after)).getchannel('A'));assert not al[:20].any() and not al[108:].any()
   elif kind=='faction name':texture_check(before,after,[(0,0,256,64)])
   elif e.name.endswith('top_00'):
    expected=bytearray(before);struct.pack_into('>ff',expected,16+89*176+32,1.25,1.25);assert after==expected
   elif e.name.endswith('common_013_ID_HQ'):
    texture_check(before,after,[(0,0,280,128)]);al=np.array(unpack_color(decode(after)).getchannel('A'));assert not al[56:72,:280].any()
   elif e.name.endswith('tenka_005_ID_HQ'):texture_check(before,after,[(672,0,824,128),(848,96,944,128)])
   else:raise AssertionError(e.name)
assert count==report['changed_resources'] and oldrows is not None
smith=arc.parse_arc(OUT/'root'/report['files'][0]['path'])
source=arc.parse_arc(ROM/'eng/tenka/smith.arc');csa=arc.unpack(source.entries[24]);mp={chr(i):struct.unpack_from('>H',csa,8+2*i)[0] for i in range(128)};tnf=arc.unpack(source.entries[0]);adv=lambda ch:struct.unpack_from('>H',tnf,32+mp[ch]*8+6)[0]
texts=json.loads((O/'TRANSLATIONS.json').read_text());widths={k:max(sum(adv(ch) for ch in line) for line in s.split('\n')) for k,s in texts.items()}
assert widths['332']<sum(adv(ch) for ch in 'Profitable Business 1')*.7
assert max(widths.values())<720
result=dict(status='pass',archives=report['archives'],resources=count,unchanged_resources=report['untouched_resources'],checks=['Archive structure and unchanged compressed entries','Allowed texture blocks only','Native player slot separation','Transparent nameplate margins','Only intended layout floats','GSM record count and 16 targeted records','English glyph coverage and line widths'],max_description_width=max(widths.values()),runtime_verified=False)
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(result,indent=2));print(result)

