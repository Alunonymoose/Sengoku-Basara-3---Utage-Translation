from pathlib import Path
import json,struct,zlib,hashlib,zipfile
W=Path(__file__).parent;OUT=W/'release';ROOT=Path(r'E:\Utage Patching New');report=json.loads((OUT/'VALIDATION.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
def parse(data):
 assert data[:4]==b'\0CRA';version,n=struct.unpack_from('>HH',data,4);rows=[]
 for i in range(n):
  h=data[8+i*80:88+i*80];typ,size,packed,off=struct.unpack_from('>IIII',h,64);blob=data[off:off+size];assert len(blob)==size
  try:raw=zlib.decompress(blob)
  except zlib.error:raw=blob
  rows.append((h[:64],typ,packed,blob,raw))
 return version,rows
unchanged=changed=lsp=0
with zipfile.ZipFile(OUT/'BACKUP_PRE_V3.zip') as bk:
 assert bk.testzip() is None
 for rec in report['files']:
  rel=rec['path'];old=bk.read(rel);new=(OUT/'root'/rel).read_bytes();assert sha(old)==rec['source_sha256'] and sha(new)==rec['sha256']
  va,a=parse(old);vb,b=parse(new);assert va==vb and len(a)==len(b)
  ids={r['index']:r for r in rec['changes']}
  for i,(x,y) in enumerate(zip(a,b)):
   assert x[:3]==y[:3]
   if i in ids:
    assert sha(x[4])==ids[i]['before'] and sha(y[4])==ids[i]['after'];assert x[4][:20]==y[4][:20] and len(x[4])==len(y[4]);changed+=1
   else:assert x[3]==y[3];unchanged+=1
   if x[1]==0x60DD1B16:assert x[4]==y[4];lsp+=1
  assert not any(s in rel for s in ['/jpn/','/demo/','msg_','tenka_msg000','tenka_msg001'])
# Texture block proof is independent of the rebuild utility.
import sys
sys.path.insert(0,str(W));from common import arc,ROM,xet_info,decode,unpack_color
orig=arc.unpack(arc.parse_arc(ROM/'jpn/quest/menu.arc').entries[35]);new=(W/'charasele_v3.tex').read_bytes();info=xet_info(orig);base=info['texture_offset'];cells=json.loads((W/'CHARASELE_BUILD.json').read_text())['cells'];allowed=set()
for c in cells:
 x0,y0,x1,y1=c['rect'];allowed.update(y*(info['width']//4)+x for y in range(y0//4,y1//4) for x in range(x0//4,x1//4))
for i in range(info['payload_size']//16):
 if i not in allowed:assert orig[base+i*16:base+(i+1)*16]==new[base+i*16:base+(i+1)*16]
# Reward backgrounds and star assets exactly match native source blocks.
orig=arc.unpack(arc.parse_arc(ROM/'jpn/quest/menu.arc').entries[30]);new=(W/'quest002_v3.tex').read_bytes();info=xet_info(orig);base=info['texture_offset']
for x0,y0,x1,y1 in [(0,192,464,256),(216,256,264,304),(264,256,296,304),(0,352,216,400)]:
 for y in range(y0//4,y1//4):
  for x in range(x0//4,x1//4):
   off=base+(y*(info['width']//4)+x)*16;assert orig[off:off+16]==new[off:off+16]
# All 161 name replacements remain within their original dimensions and row boundaries.
for rec in json.loads((W/'NAMES_BUILD.json').read_text()):
 im=unpack_color(decode(Path(rec['path']).read_bytes()));mask=im.getchannel('A')
 for lab in rec['labels']:
  row=lab['row'];bb=mask.crop((0,48*row,256,48*(row+1))).point(lambda v:255 if v>20 else 0).getbbox();assert bb and bb[0]>=2 and bb[2]<=254 and bb[1]>=4 and bb[3]<=44,(rec['key'],lab,bb)
result=dict(status='pass',archives=report['archives'],changed_resources=changed,untouched_compressed_resources=unchanged,untouched_lsp_resources=lsp,selection_frames_original_blocks=True,reward_row_original_blocks=True,stars_original_blocks=True,name_row_bounds_pass=True,runtime_verified=False)
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
