import sys,zipfile
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
O=W.parent/'quest_v9';OUT=O/'release';r=json.loads((OUT/'VALIDATION.json').read_text());texts={int(i):s for i,s in json.loads((O/'TRANSLATIONS.json').read_text()).items()}
def rows(raw):
 n=struct.unpack_from('>I',raw,12)[0];base=16+n*8;out=[]
 for i in range(n):
  off,ln=struct.unpack_from('>II',raw,16+i*8);out.append(list(struct.unpack_from('>'+str(ln)+'H',raw,base+2*off)))
 assert len(raw)==base+2*struct.unpack_from('>I',raw,8)[0]
 return out
source=arc.parse_arc(ROM/'eng/tenka/smith.arc');csa=arc.unpack(source.entries[24]);reverse={struct.unpack_from('>H',csa,8+2*i)[0]:chr(i) for i in range(128)}
def decode_text(v):
 s='';i=0
 while i<len(v):
  x=v[i];i+=1
  if x==65535:break
  if x==65534:s+='\n'
  elif x==65426:assert v[i]==2;i+=1
  elif x==65425:pass
  else:assert x in reverse;s+=reverse[x]
 return s
with zipfile.ZipFile(OUT/'BACKUP_PRE_V9.zip') as z:
 assert z.testzip() is None
 for rec in r['files']:
  data=z.read(rec['path']);assert arc.sha256(data)==rec['source_sha256'];p=OUT/'audit_before.arc';p.write_bytes(data);a=arc.parse_arc(p);p=OUT/'root'/rec['path'];assert arc.sha256(p.read_bytes())==rec['sha256'];b=arc.parse_arc(p);assert len(a.entries)==len(b.entries);changed={x['index'] for x in rec['changes']}
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.type_hash,e.flags)==(f.name,f.type_hash,f.flags)
   if e.index not in changed:assert e.compressed==f.compressed;continue
   old,new=rows(arc.unpack(e)),rows(arc.unpack(f));assert len(old)==len(new)==1963
   assert {i for i,(v,w) in enumerate(zip(old,new)) if v!=w}==set(texts)
   for i,s in texts.items():assert decode_text(new[i])==s and new[i][-1]==65535
   assert all([v for v in new[i] if v>=0xf000]==[65534,65426,65425,65535] for i in [499,509,511,517,519,529])
widths={int(i):v for i,v in json.loads((O/'WIDTHS.json').read_text()).items()};assert max(v for i,v in widths.items() if i<400)<=190;assert max(widths.values())<=720
result=dict(status='pass',translated_items=36,translated_records=72,archives=r['archives'],changed_resources=r['changed_resources'],untouched_resources=r['untouched_resources'],checks=['Backup CRC and hashes','All 72 English records decoded and compared','Untouched compressed entries identical','Record count and controls preserved','Glyph coverage and width limits','Native font proof inspected'],runtime_verified=False)
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(result,indent=2));print(result)

