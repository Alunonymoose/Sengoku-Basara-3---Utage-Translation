#!/usr/bin/env python3
"""Apply a generated whole-dialogue ROOT_READY patch with automatic backup."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path

def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--nativeps3',type=Path,required=True); ap.add_argument('--workspace',type=Path,required=True)
 a=ap.parse_args(); manifest=a.workspace/'manifest.json'; patch=a.workspace/'ROOT_READY'/'rom'/'eng'/'id'; live=a.nativeps3/'rom'/'eng'/'id'; backup=a.workspace/'BACKUP_BEFORE_APPLY'/'rom'/'eng'/'id'
 m=json.loads(manifest.read_text(encoding='utf-8')); changed=[r for r in m['files'] if r.get('status')=='REPAIRED_STATICALLY_VERIFIED']
 if not changed: raise SystemExit('No repaired archives in manifest.')
 backup.mkdir(parents=True,exist_ok=True); applied=[]
 for r in changed:
  name=r['file']; src=patch/name; dst=live/name; bak=backup/name
  if not src.exists() or not dst.exists(): raise SystemExit(f'Missing patch/live file: {name}')
  # Refuse to apply over a different source than was audited.
  if sha(dst)!=r['input_sha256']:
   raise SystemExit(f'{name}: live SHA changed since audit; refusing to overwrite. Rebuild the patch from the current live tree.')
  shutil.copy2(dst,bak); shutil.copy2(src,dst)
  if sha(dst)!=r['output_sha256']:
   raise SystemExit(f'{name}: post-copy SHA verification failed')
  applied.append(name)
 result={'status':'APPLIED_AND_SHA_VERIFIED','files_applied':len(applied),'backup_root':str(backup),'files':applied}
 (a.workspace/'APPLY_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
