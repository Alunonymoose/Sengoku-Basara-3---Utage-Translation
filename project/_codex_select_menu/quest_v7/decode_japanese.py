exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
import zipfile,pickle,hashlib
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7')
def glyphs(a):
 t=next(arc.unpack(e) for e in a.entries if e.type_hash==0x1d609ffb);pages={};result={}
 for e in a.entries:
  if e.name.startswith('msg\\') and e.name.endswith('_ID_HQ') and e.type_hash==0x241f5deb:
   try:pg=int(e.name.split('_')[-3]);pages[pg]=np.array(decode(arc.unpack(e)))[:,:,3]
   except (ValueError,KeyError):pass
 for i in range(struct.unpack_from('>I',t,8)[0]):
  gid,x,y,w=struct.unpack_from('>4H',t,32+i*8);pg=gid>>8
  if pg not in pages:continue
  cell=pages[pg][y*2:y*2+54,x*2:x*2+56]
  if not cell.size:continue
  sig=np.array(Image.fromarray(cell).resize((14,14),Image.Resampling.BILINEAR))>110
  result[i]=(gid,sig)
 return result
with zipfile.ZipFile(ROOT/'utage_translation_workset.zip') as z:maps=pickle.loads(z.read('work/glyph_maps.pkl'))
lookup={}
for name,mp in maps.items():
 p=ROM/'jpn/id'/name
 if not p.exists():continue
 for i,(gid,sig) in glyphs(arc.parse_arc(p)).items():
  if gid in mp:lookup.setdefault(sig.tobytes(),set()).add(mp[gid])
print('Reference signatures',len(lookup))
target=glyphs(arc.parse_arc(ROM/'eng/tenka/smith.arc'));resolved={};missing=[]
for i,(gid,sig) in target.items():
 values=lookup.get(sig.tobytes(),set())
 if len(values)==1:resolved[i]=next(iter(values))
 else:missing.append(i)
(O/'GLYPH_MAP.json').write_text(json.dumps(resolved,ensure_ascii=False,indent=2),encoding='utf-8')
print('Matched',len(resolved),'missing',len(missing))
for idx in [1,25]:
 rows=json.loads((O/f'shop_{idx}.json').read_text())
 a=arc.parse_arc(ROM/'eng/tenka/smith.arc');c=arc.unpack(a.entries[24]);rev={struct.unpack_from('>H',c,8+i*2)[0]:chr(i) for i in range(128)};rev.pop(65535,None)
 for r in rows:r['jp']=''.join(rev.get(v,resolved.get(v,'\n' if v==65534 else '' if v==65535 else '<%d>'%v)) for v in r['values'])
 (O/f'DECODED_{idx}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
