from common import *
from PIL import ImageFilter,ImageDraw
report=json.loads((V2/'rewards/REWARD_CANDIDATES.json').read_text());outdir=W/'names';outdir.mkdir(exist_ok=True)
master=Image.open(W/'name_lettering_master.png').convert('L')
# Detect seven separated rows in the generated white-on-black master.
x=np.asarray(master);used=(x>100).sum(axis=1)>10;bands=[];start=None
for y,v in enumerate([*used,False]):
 if v and start is None:start=y
 if not v and start is not None:
  if y-start>10:bands.append((start,y))
  start=None
assert len(bands)==7,bands
newnames=['Shingen Takeda','Hisahide Matsunaga','Sorin Otomo','Kazumasa Sogo','Kanenaka Shichijo','Buddha-Faced Kumahachi','Motosuke Kunishi']
new={txt:master.crop((0,a,master.width,b)) for txt,(a,b) in zip(newnames,bands)}
records=[]
for rec in report['candidate_resources']:
 raw=Path(rec['path']).read_bytes();old=decode(raw);rgba=Image.new('RGBA',old.size,(0,0,0,0));labs=[]
 for lab in rec['labels']:
  row=lab['row'];txt=lab['text'];mask=new.get(txt)
  if mask is None:mask=old.getchannel('G').crop((0,row*48,256,row*48+48))
  bb=mask.point(lambda v:255 if v>30 else 0).getbbox();assert bb,(rec['key'],txt)
  mask=mask.crop(bb)
  # Uniform visible height makes long names as clear as short names, bounded to the native slot.
  width=min(242,round(mask.width*32/mask.height));mask=mask.resize((width,32),Image.Resampling.LANCZOS)
  mask=mask.point(lambda v:0 if v<12 else min(255,round(v*1.4)))
  coverage=Image.new('L',(256,48));coverage.paste(mask,((256-width)//2,8))
  outline=coverage.filter(ImageFilter.MaxFilter(5))
  cell=Image.new('RGBA',(256,48),(25,17,5,0));cell.putalpha(outline)
  ink=Image.new('RGBA',(256,48),(255,248,226,0));ink.putalpha(coverage);cell.alpha_composite(ink)
  rgba.alpha_composite(cell,(0,row*48));labs.append(dict(row=row,text=txt,ink_size=[width,32],coverage_bbox=outline.getbbox(),new_master=txt in new))
 packed=pack_color(rgba);edited=patch_bc3_rect(raw,packed,(0,0,rgba.width,rgba.height));target=outdir/(rec['key']+'.tex');target.write_bytes(edited)
 preview(unpack_color(decode(edited)),target.with_suffix('.png'),(120,97,29,255));records.append(dict(key=rec['key'],path=str(target),sha256=arc.sha256(edited),labels=labs))
(W/'NAMES_BUILD.json').write_text(json.dumps(records,indent=2))
# Four names from user's screen, rendered at physical texture scale over the reward colour.
requested=[('cp_name_pl_028_id_hq',0),('cp_name_nak_009_id_hq',0),('cp_name_nak_023_id_hq',3),('cp_name_nak_026_id_hq',1)]
# Find Yorisato by ledger rather than relying on an index guess.
requested[2]=next((r['key'],l['row']) for r in records for l in r['labels'] if l['text']=='Yorisato Gamo')
proof=Image.new('RGBA',(576,260),(120,97,29,255));d=ImageDraw.Draw(proof);d.text((10,7),'Before (V2)',fill='white');d.text((298,7),'After (V3)',fill='white')
for i,(key,row) in enumerate(requested):
 for col,p in enumerate([V2/'rewards/candidate'/(key+'.tex'),outdir/(key+'.tex')]):
  cell=unpack_color(decode(p.read_bytes())).crop((0,row*48,256,row*48+48));proof.alpha_composite(cell,(10+288*col,35+52*i))
proof.convert('RGB').save(W/'REWARD_NAME_COMPARISON.png')
print('Built',len(records),'reward name sheets')
