#!/usr/bin/env python3
"""BASARA 3 Utage English v0.1 beta patch installer.
Applies only hash-verified binary deltas to the user's own game backup.
No network calls, no in-place mutation.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sys,time,zipfile
from pathlib import Path

def say(*x):print(*x,flush=True)
def sha(data):return hashlib.sha256(data).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
 return h.hexdigest()
def path_in(root,rel):
 rel=rel.replace("\\","/")
 p=Path(rel)
 if not rel or p.is_absolute() or ".." in p.parts or ":" in rel or p.as_posix()!=rel:
  raise ValueError("Unsafe file name in manifest: "+rel)
 return root/p
def find_game(root):
 root=Path(root).resolve()
 if (root/"PS3_GAME/USRDIR/EBOOT.BIN").exists():root=root/"PS3_GAME"
 if not (root/"USRDIR/EBOOT.BIN").is_file() or not (root/"PARAM.SFO").is_file():
  raise ValueError("Choose your extracted Japanese PS3_GAME folder (with USRDIR and PARAM.SFO)")
 return root
def load_manifest(root):
 path=root/"RC1_MANIFEST.json"
 meta=json.loads(path.read_text(encoding="utf8"))
 assert meta["schema"]=="UTAGE_EN_PATCH_V1"
 assert len(meta["files"])>=100
 return meta

def verify_source(original,files):
 paths={}
 for x in files:
  if x["action"] not in ("COPY","PATCH"):continue
  rel=x["source"]
  pair=(rel,x["source_sha256"])
  if rel in paths and paths[rel]!=x["source_sha256"]:
   raise ValueError("Source mapping conflict: "+rel)
  paths[rel]=x["source_sha256"]
 say("Checking your own Japanese game files:",len(paths),"unique sources")
 for n,(name,hash_expected) in enumerate(paths.items(),1):
  p=path_in(original,name)
  if not p.is_file():raise ValueError("Missing original Japanese game file: "+name)
  digest=sha_file(p)
  if digest!=hash_expected:raise ValueError("Wrong game dump / file version: "+name+
    "\nExpected SHA-256: "+hash_expected+"\nFound SHA-256: "+digest+
    "\nYour originals are unchanged. Install the supported Japanese disc dump first.")
  if n%500==0:say("  Source check",n,"/",len(paths))
 return len(paths)

def run(source,dest,verify_only=False):
 import bsdiff4,zstandard as zstd
 release=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
 # The patch zip stays alongside the executable, never hidden inside the app.
 package_root=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
 manifest=load_manifest(package_root)
 src=find_game(source)
 target=Path(dest).resolve()
 if target==src or src in target.parents or target in src.parents:
  raise ValueError("Output must be a separate folder, not your original game")
 if target.exists():raise FileExistsError("Output folder already exists; nothing was overwritten: "+str(target))
 files=manifest["files"]
 verify_source(src,files)
 package=package_root/"RC1_PATCHES.zip"
 if not package.exists():raise FileNotFoundError("RC1_PATCHES.zip must be beside this installer")
 say("Checking patch archive...")
 with zipfile.ZipFile(package) as z:
  names=set(z.namelist())
  for item in files:
   if item["action"] in ("PATCH","ADD") and item["data"] not in names:
    raise ValueError("Missing delta payload: "+item["data"])
 say("Source and patch archive layout look correct.")
 if verify_only:
  say("PASSED: game input checks. Ready to build the English game in a new folder.")
  return
 # Reserve for a complete independent game copy plus patch outputs.
 target.parent.mkdir(parents=True,exist_ok=True)
 rawsize=sum(p.stat().st_size for p in src.rglob("*") if p.is_file())
 free=shutil.disk_usage(target.parent).free
 if free < rawsize+2*1024*1024*1024:
  raise OSError(f"Not enough space; need roughly {(rawsize+2*1024**3)/1024**3:.1f} GiB free")
 staging=target.with_name(target.name+".INSTALLING")
 if staging.exists():raise FileExistsError("Unfinished previous install found: "+str(staging))
 say("Creating a separate game copy. Original remains untouched.")
 staging.mkdir(parents=True)
 try:
  # Copy your own dump, omitting pre-existing unofficial English mods.
  # No hard links: safe to remove/change staging without touching original.
  def ignore_eng(folder,children):
   p=Path(folder)
   if p.name=="rom" and "eng" in children:return {"eng"}
   return set()
  shutil.copytree(src,staging,dirs_exist_ok=True,ignore=ignore_eng)
  decomp=zstd.ZstdDecompressor()
  with zipfile.ZipFile(package) as z:
   for i,item in enumerate(files,1):
    action=item["action"];out=path_in(staging,item["destination"])
    out.parent.mkdir(parents=True,exist_ok=True)
    if action=="COPY":
     # No delta: copy the original Japanese resource into the English route.
     orig=path_in(src,item["source"])
     shutil.copy2(orig,out)
    elif action in ("PATCH","ADD"):
     data=z.read(item["data"])
     if sha(data)!=item["data_sha256"]:raise ValueError("Corrupted patch payload: "+item["destination"])
     if action=="PATCH":
      orig=path_in(src,item["source"]).read_bytes()
      rebuilt=bsdiff4.patch(orig,data)
     else:
      rebuilt=decomp.decompress(data,max_output_size=item["target_size"]+1)
     if len(rebuilt)!=item["target_size"] or sha(rebuilt)!=item["target_sha256"]:
      raise ValueError("Patch output failed verification: "+item["destination"])
     out.write_bytes(rebuilt)
    else:raise ValueError("Unknown patch action: "+action)
    if action=="COPY" and sha_file(out)!=item["target_sha256"]:
     raise ValueError("Copied Japanese file did not match expected English route: "+item["destination"])
    if i%250==0:say("Installing",i,"/",len(files))
  # The Japanese original route stays copied straight from the player's own game.
  (staging/"UTAGE_ENGLISH_RC1_INSTALL_RECEIPT.json").write_text(json.dumps({
   "status":"SUCCESS","release":manifest["version"],"manifest_sha256":sha_file(package_root/"RC1_MANIFEST.json"),
   "files":len(files),"original_game_path":str(src),"original_untouched":True},indent=2),encoding="utf8")
  staging.rename(target)
  # Preserve the disc marker for game discovery from the player's own game dump.
  disc_marker=src.parent/"PS3_DISC.SFB"
  if disc_marker.is_file():
   marker_dest=target.parent/"PS3_DISC.SFB"
   if not marker_dest.exists():shutil.copy2(disc_marker,marker_dest)
  say("\nSUCCESS: English game is at",target)
  say("Keep the original Japanese PS3_GAME folder. You can delete this English copy to undo the installation.")
 except Exception:
  say("Installation aborted. Your original game was not modified. Incomplete output:",staging)
  raise

def main():
 ap=argparse.ArgumentParser(description="Install English v0.1 Beta on your own Japanese PS3_GAME dump")
 ap.add_argument("--source",help="Your Japanese PS3_GAME folder")
 ap.add_argument("--output",help="New folder for English PS3_GAME")
 ap.add_argument("--verify-only",action="store_true",help="Check compatibility without writing anything")
 args=ap.parse_args()
 if args.source and args.output:
  run(args.source,args.output,args.verify_only);return
 try:
  import tkinter as tk
  from tkinter import filedialog,messagebox
  root=tk.Tk();root.withdraw()
  messagebox.showinfo("Utage English v0.1 Beta","Select the PS3_GAME folder from your own Japanese game dump. Nothing in it will be changed.")
  source=filedialog.askdirectory(title="Select original Japanese PS3_GAME folder")
  if not source:return
  place=filedialog.askdirectory(title="Select an EMPTY destination parent folder for your English game")
  if not place:return
  target=Path(place)/"Sengoku_BASARA_3_Utage_English_v0.1_Beta"/"PS3_GAME"
  target.parent.mkdir(exist_ok=True)
  try:
   run(source,target,args.verify_only)
   messagebox.showinfo("Complete","Installed in:\n"+str(target)+"\n\nYour original game is untouched.")
  except Exception as exc:
   messagebox.showerror("Install not completed",str(exc))
   raise
 finally:
  try:root.destroy()
  except Exception:pass
if __name__=="__main__":
 try:main()
 except Exception as error:
  say("ERROR:",str(error))
  sys.exit(1)
