from pathlib import Path
import bsdiff4,zstandard as zstd
import json,hashlib,zipfile,shutil,time,datetime,sys
W=Path("E:/BASARA_WORK/jobs/UTAGE_RC1_RELEASE_20261010")
O=Path("E:/Utage Patching/PS3_GAME")
T=Path("E:/Utage Patching New/PS3_GAME")
R=W/"Sengoku_BASARA_3_Utage_English_v0.1_Beta_CORE_PATCH"
R.mkdir(exist_ok=True)
scan=W/"RELEASE_SOURCE_TARGET_AUDIT.json"
assert scan.exists(),"Wait for baseline hash scan"
raw_entries=json.loads(scan.read_text(encoding="utf8"))["files"]
# Core release: media streamed from the original game; 27 modified PAM files are a separate add-on.
entries=[x for x in raw_entries if not x["target"].startswith("USRDIR/nativePS3/movie/") and not (x["action"]=="COPY" and x["base"]==x["target"])]
print("CORE_RELEASE_INPUTS",len(entries),"OMITTED_MOVIES",sum(x["action"]=="PATCH" and x["target"].startswith("USRDIR/nativePS3/movie/") for x in raw_entries),flush=True)
assert 4000<len(entries)<7000,len(entries)
def h(b):return hashlib.sha256(b).hexdigest()
def hd(path):
 f=hashlib.sha256()
 with path.open("rb") as src:
  for chunk in iter(lambda:src.read(8*1024*1024),b""):f.update(chunk)
 return f.hexdigest()
manifest=[]
rebuild_counts={"COPY":0,"PATCH":0,"ADD":0}
payload_zip=R/"RC1_PATCHES.zip"
if payload_zip.exists():raise FileExistsError("Refusing overwrite: "+str(payload_zip))
t=time.monotonic()
with zipfile.ZipFile(payload_zip,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as pack:
 for i,record in enumerate(entries,1):
  rel=record["target"];action=record["action"]
  target=T/rel
  assert target.is_file(),rel
  if target.stat().st_size!=record["target_size"]:
   raise RuntimeError("Live target changed size during release build: "+rel)
  item={"destination":rel,"target_sha256":record["target_sha"],
     "target_size":record["target_size"],"action":action}
  if action in ("COPY","PATCH"):
   item["source"]=record["base"];item["source_sha256"]=record["base_sha"]
   item["source_size"]=record["base_size"]
  if action!="COPY":
   data=target.read_bytes()
   if h(data)!=record["target_sha"]:raise RuntimeError("Live target changed during release build: "+rel)
   if action=="PATCH":
    original=(O/record["base"]).read_bytes()
    if h(original)!=record["base_sha"]:raise RuntimeError("Japanese baseline changed: "+record["base"])
    patch=bsdiff4.diff(original,data)
    if bsdiff4.patch(original,patch)!=data:
     raise RuntimeError("Reconstruction failed: "+rel)
    path=f"delta/{i:06d}.bsdiff"
   else:
    patch=zstd.ZstdCompressor(level=9,threads=2).compress(data)
    if zstd.ZstdDecompressor().decompress(patch,max_output_size=len(data)+1)!=data:
     raise RuntimeError("New asset decompression failed: "+rel)
    path=f"new/{i:06d}.zst"
   item.update({"data":path,"data_sha256":h(patch),"data_size":len(patch)})
   pack.writestr(path,patch,compress_type=zipfile.ZIP_STORED)
  manifest.append(item);rebuild_counts[action]+=1
  if i%300==0:print("PATCH_PAYLOAD_PROGRESS",i,len(entries),"actions",rebuild_counts,
     "ZIP_GB",round(payload_zip.stat().st_size/1e9,3),"minutes",round((time.monotonic()-t)/60,2),flush=True)
print("PATCHES_BUILT",rebuild_counts,"SECONDS",round(time.monotonic()-t,1),flush=True)
meta={"schema":"UTAGE_EN_PATCH_V1","version":"v0.1-beta-core-2026-10-10",
 "source_game":"Sengoku BASARA 3 Utage Japan PS3 extracted disc dump",
 "source_eboot_sha256":next(x["source_sha256"] for x in manifest if x["destination"]=="USRDIR/EBOOT.BIN"),
 "target_eboot_sha256":next(x["target_sha256"] for x in manifest if x["destination"]=="USRDIR/EBOOT.BIN"),
 "source_provenance":"Pristine base E:/Utage Patching/PS3_GAME; installer independently validates every source needed",
 "user_game_required":True,"patch_only":True,
 "media_note":"Original Japanese PAM movies are preserved. A separate cinematic patch is planned.",
 "files":manifest}
(R/"RC1_MANIFEST.json").write_text(json.dumps(meta,indent=1,ensure_ascii=False),encoding="utf8")
(W/"PATCH_BUILD_VERIFIED.json").write_text(json.dumps({"built_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "payload_bytes":payload_zip.stat().st_size,"actions":rebuild_counts,
 "manifest_sha256":hd(R/"RC1_MANIFEST.json"),"payload_sha256":hd(payload_zip),
 "seconds":round(time.monotonic()-t,2)},indent=2),encoding="utf8")
print("RC1_PATCHES_VERIFIED",payload_zip.stat().st_size,flush=True)
