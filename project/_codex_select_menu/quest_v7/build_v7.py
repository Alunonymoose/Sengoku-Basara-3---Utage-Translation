import sys,re,zipfile,hashlib
from collections import defaultdict
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v5')
from build_v5 import *
V5=O; O=W.parent/'quest_v7'; plan=defaultdict(dict); notes=defaultdict(dict)
def put(p,i,out,kind):
 p=Path(p);plan[p][i]=out;notes[p][i]=kind

# Source art is ImageGen lettering; only key removal and native sprite packing here.
im=Image.open(O/'names_key.png').convert('RGBA');a=np.array(im);r,g,b=[a[:,:,i].astype(int) for i in range(3)]
bg=(r>160)&(g>45)&(g<205)&(b<100)&(r>g+35)
a[:,:,3]=np.array(Image.fromarray((~bg).astype('uint8')*255).filter(ImageFilter.MinFilter(3)));a[a[:,:,3]==0,:3]=0;im=Image.fromarray(a)
sprites=[]
for y0,y1 in [(0,150),(150,290),(290,440),(440,580),(580,720),(720,860),(860,1024)]:
 for x0,x1 in [(300,795),(795,1250)]:
  s=im.crop((x0,y0,x1,y1));s=s.crop(s.getbbox());sprites.append(s)
owners=json.loads((O/'HEADER_OWNERS.json').read_text());proof=Image.new('RGBA',(1024,512),(220,218,178,255))
for row in owners:
 p=Path(row['path']);idx=row['index'];name=row['name'];a=arc.parse_arc(p);raw=arc.unpack(a.entries[idx]);out=raw
 if '\\name\\name_' in name:
  n=int(re.search(r'name_(\d+)_',name)[1])
  if n<16:continue
  c=cell(sprites[n-16],(256,128),(244,70));out=paint(raw,c,(0,0,256,128))
  proof.alpha_composite(unpack_color(decode(out)),(((n-16)%4)*256,((n-16)//4)*128))
 elif name.endswith('common_013_ID_HQ'):
  # Native sampling uses 64-pixel rows. Old sprites wrongly began row 2 at y=50.
  src=unpack_color(decode(raw));c=Image.new('RGBA',(280,128))
  for source,dest,size in [((0,0,196,49),(0,0),(196,64)),((0,50,196,97),(0,64),(196,64)),((198,0,280,49),(196,0),(84,64)),((198,50,280,97),(196,64),(84,64))]:
   if source[0]==198:
    jp=arc.parse_arc(ROM/'jpn/tenka/tenka_id.arc');original=unpack_color(decode(arc.unpack(next(e for e in jp.entries if e.name.endswith('common_013_ID_HQ')))))
    s=original.crop((196,0 if source[1]==0 else 64,280,64 if source[1]==0 else 128))
   else:s=src.crop(source)
   s=s.crop(s.getbbox());c.alpha_composite(cell(s,size,(size[0]-8,48)),dest)
  out=paint(raw,c,(0,0,280,128));preview(unpack_color(decode(out)),O/'PLAYER_HEADER.png',(215,217,180,255))
 elif name.endswith('tenka_005_ID_HQ'):
  # Keep gold decoration intact; replace only the five native label cells.
  for k,rect in [(0,(672,0,824,32)),(1,(672,32,824,64)),(2,(672,64,824,96)),(4,(672,96,824,128)),(3,(848,96,944,128))]:
   s=Image.open(V5/f'master_sprite_{k}.png').convert('RGBA')
   if k==4:s=Image.open(W.parent/'quest_v6/quick_sprite.png').convert('RGBA')
   out=paint(out,cell(s,(rect[2]-rect[0],32),(rect[2]-rect[0]-4,30)),rect)
  preview(unpack_color(decode(out)),O/'MAP_HEADING.png',(216,220,188,255))
 elif name.endswith('top_00'):
  out=bytearray(raw);ns=lsp_parse(raw)
  n=ns[89];assert n['name']=='2_0_2' and n['scale'][0]<1.01,n
  # This parent owns only the mode title; enlarge within the wide gold banner.
  assert [t['index'] for t in ns if t['parent']==89]==[90]
  struct.pack_into('>ff',out,16+89*176+0x20,1.25,1.25);out=bytes(out)
 else:continue
 put(p,idx,out,'map header' if '\\name\\' not in name else 'character name')
proof.convert('RGB').save(O/'NAMES_DECODED.png')

def gsm_rows(raw):
 n=struct.unpack_from('>I',raw,12)[0];base=16+8*n
 return [list(struct.unpack_from('>'+str(ln)+'H',raw,base+2*off)) for off,ln in [struct.unpack_from('>II',raw,16+i*8) for i in range(n)]]
def gsm_build(raw,rows):
 pool=[];tab=bytearray()
 for v in rows:tab+=struct.pack('>II',len(pool),len(v));pool+=v
 h=bytearray(raw[:16]);struct.pack_into('>I',h,8,len(pool))
 return bytes(h)+tab+struct.pack('>'+str(len(pool))+'H',*pool)

# Faction label shares the same faint placeholder problem as Hisahide's name.
labels=Image.open(O/'labels_key.png').convert('RGBA');aa=np.array(labels);rr,gg,bb=[aa[:,:,i].astype(int) for i in range(3)];bg=(rr>160)&(gg>45)&(gg<205)&(bb<100)&(rr>gg+35)
aa[:,:,3]=np.array(Image.fromarray((~bg).astype('uint8')*255).filter(ImageFilter.MinFilter(3)));aa[aa[:,:,3]==0,:3]=0
faction=Image.fromarray(aa).crop((0,0,1536,280));faction=faction.crop(faction.getbbox())

# The first three four-piece item families shown in the report.
translations={}
for i in range(4):
 translations[332+i]=f'Profit Bonus {i+1}'
 translations[532+i]='Gain a treasure chest after battle. Four improve its quality.\nNo effect in Japan\'s Event.'
 translations[536+i]='+1,000 EXP each. Four give +3,000 more. Wearer only.\nNo effect in Japan\'s Event.'
 translations[540+i]='+1,000 Z each. Four give +6,000 more.\nNo effect in Japan\'s Event.'
base=arc.parse_arc(ROM/'eng/tenka/smith.arc');base_gsm=arc.unpack(base.entries[25]);base_csa=arc.unpack(base.entries[24])
cmap={chr(i):struct.unpack_from('>H',base_csa,8+2*i)[0] for i in range(128)}
def encode(s):
 vals=[]
 for ch in s:
  if ch=='\n':vals.append(65534);continue
  assert ch in cmap and cmap[ch]!=65535,repr(ch)
  vals.append(cmap[ch])
 return vals
rows=gsm_rows(base_gsm)
for idx,s in translations.items():
 if '\n' in s:
  first,last=s.split('\n');rows[idx]=encode(first)+[65534,65426,2]+encode(last)+[65425,65535]
 else:rows[idx]=encode(s)+[65535]
newgsm=gsm_build(base_gsm,rows)
assert len(gsm_rows(newgsm))==len(rows)
# Patch identical archive-local copies, never dialogue or Claude's conquest messages.
for p in (ROM/'eng').rglob('*.arc'):
 if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc'] or 'demo' in p.parts:continue
 with p.open('rb') as f:
  h=f.read(8)
  if h[:4]!=b'\0CRA':continue
  tab=f.read(struct.unpack_from('>H',h,6)[0]*80)
 hits=[i for i in range(len(tab)//80) if b'id_brief_r' in tab[i*80:i*80+64] or b'army_026_ID_HQ' in tab[i*80:i*80+64]]
 if not hits:continue
 ar=arc.parse_arc(p)
 for idx in hits:
  if ar.entries[idx].name.endswith('army_026_ID_HQ'):
   raw=arc.unpack(ar.entries[idx]);dims=decode(raw).size
   if dims!=(256,64):
    print("Skipped different atlas",p,idx,dims);continue
   out=paint(raw,cell(faction,(256,64),(250,40)),(0,0,256,64));put(p,idx,out,'faction name');preview(unpack_color(decode(out)),O/'FACTION_DECODED.png',(215,220,182,255))
  elif arc.unpack(ar.entries[idx])==base_gsm:put(p,idx,newgsm,'shop text')
(O/'TRANSLATIONS.json').write_text(json.dumps(translations,indent=2))
OUT=O/'release';ST=OUT/'root';ST.mkdir(parents=True,exist_ok=True);files=[]
with zipfile.ZipFile(OUT/'BACKUP_PRE_V7.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p,reps in sorted(plan.items()):
  assert p.is_relative_to(ROM/'eng') and not p.name.startswith('msg_') and p.name not in ['tenka_msg000.arc','tenka_msg001.arc']
  a=arc.parse_arc(p);reps={i:v for i,v in reps.items() if v!=arc.unpack(a.entries[i])}
  if not reps:continue
  rel=p.relative_to(ROOT).as_posix();z.writestr(rel,a.data);out=arc.rebuild(a,reps);target=ST/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(out);b=arc.parse_arc(target)
  assert len(a.entries)==len(b.entries)
  for e,f in zip(a.entries,b.entries):
   assert(e.name,e.type_hash,e.flags)==(f.name,f.type_hash,f.flags)
   if e.index in reps:assert arc.unpack(f)==reps[e.index]
   else:assert e.compressed==f.compressed
  files.append(dict(path=rel,source_sha256=arc.sha256(a.data),sha256=arc.sha256(out),changes=[dict(index=i,name=a.entries[i].name,kind=notes[p][i]) for i in reps],unchanged_resources=len(a.entries)-len(reps)))
assert any(c['kind']=='shop text' for f in files for c in f['changes'])
r=dict(status='staged',files=files,archives=len(files),changed_resources=sum(len(f['changes']) for f in files),untouched_resources=sum(f['unchanged_resources'] for f in files),runtime_verified=False)
(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2));print({k:v for k,v in r.items() if k!='files'})


