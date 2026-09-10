from pathlib import Path
import zipfile,hashlib
root=Path(r'E:\Utage Patching New');b=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v10\release\BACKUP_PRE_V10.zip')
with zipfile.ZipFile(b) as z:
 for n in z.namelist():
  if n.startswith('PS3_GAME/USRDIR/nativePS3/rom/eng/'):
   p=root/n;print(n,hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(z.read(n)).hexdigest())
