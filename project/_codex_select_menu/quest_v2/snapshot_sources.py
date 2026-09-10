from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(r'E:\Utage Patching New')
WORK=Path(__file__).resolve().parent
BASE=WORK/'baseline'
RELROOT=Path('PS3_GAME/USRDIR/nativePS3/rom/eng')
paths=sorted((ROOT/RELROOT/'quest').glob('*.arc'))+[ROOT/RELROOT/'select/c_common.arc']
manifest={}
for p in paths:
    rel=p.relative_to(ROOT).as_posix();data=p.read_bytes();h=hashlib.sha256(data).hexdigest();out=BASE/rel
    if out.exists():assert out.read_bytes()==data,'Source drift since snapshot'
    else:out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
    manifest[rel]={'sha256':h,'bytes':len(data)}
(WORK/'BASELINE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
backup=WORK/'BACKUP_PRE_QUEST_MENU_V2.zip'
if not backup.exists():
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for rel in manifest:z.write(BASE/rel,rel)
with zipfile.ZipFile(backup) as z:
    assert z.testzip() is None
    assert {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}=={n:r['sha256'] for n,r in manifest.items()}
print(json.dumps({'archives':len(manifest),'backup':str(backup),'sha256':hashlib.sha256(backup.read_bytes()).hexdigest()}))
