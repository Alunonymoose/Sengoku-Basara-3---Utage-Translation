from pathlib import Path
import json,struct,zlib,hashlib,zipfile
O=Path(__file__).parent;OUT=O/'release';r=json.loads((OUT/'VALIDATION.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
def parse(data):
 assert data[:4]==b'\0CRA';v,n=struct.unpack_from('>HH',data,4);rows=[]
 for i in range(n):
  h=data[8+i*80:88+i*80];typ,size,packed,off=struct.unpack_from('>IIII',h,64);blob=data[off:off+size];assert len(blob)==size
  try:raw=zlib.decompress(blob)
  except zlib.error:raw=blob
  rows.append((h[:64],typ,packed,blob,raw))
 return v,rows
import sys
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import xet_info
counts={};unchanged=0;lsp_fields=0
with zipfile.ZipFile(OUT/'BACKUP_PRE_V5.zip') as bk:
 assert bk.testzip() is None
 for rec in r['files']:
  old=bk.read(rec['path']);new=(OUT/'root'/rec['path']).read_bytes();assert sha(old)==rec['source_sha256'] and sha(new)==rec['sha256']
  va,a=parse(old);vb,b=parse(new);assert va==vb and len(a)==len(b);ids={c['index']:c for c in rec['changes']}
  for i,(x,y) in enumerate(zip(a,b)):
   assert x[:3]==y[:3]
   if i not in ids:assert x[3]==y[3];unchanged+=1;continue
   c=ids[i];u,v=x[4],y[4];assert sha(u)==c['before'] and sha(v)==c['after'] and len(u)==len(v)
   if c['kind'].endswith('layout'):
    expected=bytearray(u)
    for e in c['edits']:
     at=e['offset'];assert u[at:at+4].hex()==e['before'];expected[at:at+4]=bytes.fromhex(e['after']);lsp_fields+=1
    assert bytes(expected)==v
   else:
    inf=xet_info(u);base=inf['texture_offset'];assert u[:base]==v[:base];allowed=set()
    for x0,y0,x1,y1 in c['rects']:allowed.update(yy*(inf['width']//4)+xx for yy in range(y0//4,y1//4) for xx in range(x0//4,x1//4))
    for n in range(inf['payload_size']//16):
     if n not in allowed:assert u[base+n*16:base+(n+1)*16]==v[base+n*16:base+(n+1)*16]
    assert u[base+inf['payload_size']:]==v[base+inf['payload_size']:]
   counts[c['kind']]=counts.get(c['kind'],0)+1
  assert not any(s in rec['path'] for s in ['/jpn/','/demo/','msg_','tenka_msg000','tenka_msg001'])
assert counts=={'mode':14,'charasele':9,'locked':4,'mode_layout':2,'join_layout':7,'join_text':6},counts
result=dict(status='pass',archives=r['archives'],changed_resources=sum(counts.values()),untouched_compressed_resources=unchanged,copies=counts,changed_lsp_fields=lsp_fields,all_changes_within_declared_texture_cells_or_exact_layout_fields=True,runtime_verified=False)
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
