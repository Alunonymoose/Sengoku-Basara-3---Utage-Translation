from pathlib import Path
v3=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3');v4=v3.parent/'quest_v4'
s=(v3/'verify_release.py').read_text().split('# Texture block proof')[0].replace('BACKUP_PRE_V3','BACKUP_PRE_V4')
s+='''
import sys
sys.path.insert(0,r'E:\\Utage Patching New\\_codex_select_menu\\quest_v3')
from common import xet_info,decode,unpack_color,np,Image
counts={}
with zipfile.ZipFile(OUT/'BACKUP_PRE_V4.zip') as bk:
 for rec in report['files']:
  _,a=parse(bk.read(rec['path']));_,b=parse((OUT/'root'/rec['path']).read_bytes())
  for c in rec['changes']:
   x,y=a[c['index']][4],b[c['index']][4];inf=xet_info(x);base=inf['texture_offset'];allowed=set()
   for x0,y0,x1,y1 in c['rects']:allowed.update(yy*(inf['width']//4)+xx for yy in range(y0//4,y1//4) for xx in range(x0//4,x1//4))
   for n in range(inf['payload_size']//16):
    if n not in allowed:assert x[base+n*16:base+(n+1)*16]==y[base+n*16:base+(n+1)*16]
   counts[c['kind']]=counts.get(c['kind'],0)+1
for k,c in enumerate(json.loads((W/'CHARASELE_BUILD.json').read_text())['cells']):
 got=np.array(unpack_color(decode((W/'charasele_v4.tex').read_bytes())).crop(c['rect']))[:,:,3];want=np.array(Image.open(W/f'cell_{k}.png'))[:,:,3];assert not got[want==0].any(),('charasele',k)
for c in json.loads((W/'MODE_BUILD.json').read_text()):
 row,col=c['row'],int(c['state']=='normal');got=np.array(unpack_color(decode((W/'mode_select_v4.tex').read_bytes())).crop(c['rect']))[:,:,3];want=np.array(Image.open(W/f'mode_cell_{row}_{col}.png'))[:,:,3];assert not got[want==0].any(),('mode',row,col)
assert counts=={'currency':4,'mode':14,'charasele':9},counts
assert any(f['path'].endswith('/eng/init_ps3.arc') for f in report['files'])
result=dict(status='pass',archives=report['archives'],changed_resources=changed,untouched_compressed_resources=unchanged,untouched_lsp_resources=lsp,copies=counts,startup_atlas_included=True,all_changes_within_declared_texture_cells=True,all_old_text_slots_fully_replaced=True,visible_and_faint_stray_opacity_pixels=0,runtime_verified=False)
(OUT/'INDEPENDENT_CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
'''
(v4/'verify_release_v4.py').write_text(s)
