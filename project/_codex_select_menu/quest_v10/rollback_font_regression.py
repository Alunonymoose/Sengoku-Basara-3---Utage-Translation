from pathlib import Path
import zipfile,hashlib,os,json
root=Path(r'E:\Utage Patching New'); backup=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v10\release\BACKUP_PRE_V10.zip')
with zipfile.ZipFile(backup) as z:
 for name in z.namelist():
  if not name.startswith('PS3_GAME/USRDIR/nativePS3/rom/eng/'): continue
  target=root/name
  assert target.is_relative_to(root/'PS3_GAME/USRDIR/nativePS3/rom/eng')
  target.write_bytes(z.read(name))
print('restored',len([n for n in z.namelist() if n.startswith('PS3_GAME/USRDIR/nativePS3/rom/eng/')]))
