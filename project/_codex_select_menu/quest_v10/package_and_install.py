from pathlib import Path
import json,hashlib,zipfile,os
W=Path(__file__).parent;OUT=W/'release';ROOT=Path(r'E:\Utage Patching New').resolve();sha=lambda x:hashlib.sha256(x).hexdigest()
r=json.loads((OUT/'VALIDATION.json').read_text());assert json.loads((OUT/'INDEPENDENT_CHECK.json').read_text())['status']=='pass'
r.update(status='offline_validated',backup=str(OUT/'BACKUP_PRE_V10.zip'),backup_sha256=sha((OUT/'BACKUP_PRE_V10.zip').read_bytes()));(OUT/'VALIDATION.json').write_text(json.dumps(r,indent=2))
package=OUT/'Utage_Menu_V10_MASS_SHOP_TRANSLATIONS_ROOT_READY.zip'
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
 for rec in r['files']:
  p=OUT/'root'/rec['path'];assert sha(p.read_bytes())==rec['sha256'];z.write(p,rec['path'])
 for name in ['VALIDATION.json','INDEPENDENT_CHECK.json','RELEASE_NOTES.md']:z.write(OUT/name,name)
 z.write(W/'TEXT_NOTES.md','TEXT_NOTES.md')
with zipfile.ZipFile(package) as z:
 assert z.testzip() is None
 for rec in r['files']:assert sha(z.read(rec['path']))==rec['sha256']
for rec in r['files']:
 target=(ROOT/rec['path']).resolve();assert target.is_relative_to(ROOT/'PS3_GAME/USRDIR/nativePS3/rom/eng');assert sha(target.read_bytes())==rec['source_sha256'],f'Concurrent modification: {target}'
pending=[];installed=[]
try:
 for rec in r['files']:
  target=ROOT/rec['path'];temp=target.with_name(target.name+'.menu_v10_pending');assert not temp.exists();temp.write_bytes((OUT/'root'/rec['path']).read_bytes());assert sha(temp.read_bytes())==rec['sha256'];pending.append((rec,target,temp))
 for rec,target,temp in pending:
  assert sha(target.read_bytes())==rec['source_sha256'];os.replace(temp,target);assert sha(target.read_bytes())==rec['sha256'];installed.append(rec)
except Exception:
 with zipfile.ZipFile(OUT/'BACKUP_PRE_V10.zip') as bk:
  for rec in reversed(installed):
   target=ROOT/rec['path']
   if sha(target.read_bytes())==rec['sha256']:target.write_bytes(bk.read(rec['path']))
 for rec,target,temp in pending:
  if temp.exists():temp.unlink()
 raise
for rec in r['files']:assert sha((ROOT/rec['path']).read_bytes())==rec['sha256']
result=dict(status='installed_and_readback_verified',archives=len(installed),package=str(package),package_sha256=sha(package.read_bytes()),backup=r['backup'],backup_sha256=r['backup_sha256'],runtime_verified=False)
(OUT/'INSTALL_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))



