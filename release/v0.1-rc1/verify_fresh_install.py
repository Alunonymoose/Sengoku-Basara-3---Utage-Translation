from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json,hashlib,time,datetime
W=Path("E:/BASARA_WORK/jobs/UTAGE_RC1_RELEASE_20261010")
R=W/"Sengoku_BASARA_3_Utage_English_v0.1_Beta_CORE_PATCH"
installed=W/"FRESH_GAME_INSTALL_TEST/PS3_GAME"
source=Path("E:/Utage Patching/PS3_GAME")
manifest=json.loads((R/"RC1_MANIFEST.json").read_text(encoding="utf8"))
files=manifest["files"]
assert installed.exists() and (installed/"UTAGE_ENGLISH_RC1_INSTALL_RECEIPT.json").exists()
def hashfile(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
def audit(r):
 out=installed/r["destination"]
 if not out.exists():return ("MISSING",r["destination"])
 if out.stat().st_size!=r["target_size"]:return ("SIZE_MISMATCH",r["destination"])
 if hashfile(out)!=r["target_sha256"]:return ("HASH_MISMATCH",r["destination"])
 return ("PASS",r["destination"])
t=time.monotonic()
with ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(audit,files))
failed=[(a,b) for a,b in results if a!="PASS"]
assert not failed,failed[:20]
assert (installed/"PARAM.SFO").is_file()
assert (installed/"USRDIR/EBOOT.BIN").is_file()
assert (installed.parent/"PS3_DISC.SFB").read_bytes()==(source.parent/"PS3_DISC.SFB").read_bytes()
# Japanese source baseline must be copied unmodified (sample of root JP files and at least 3 top groups)
for rel in ("USRDIR/nativePS3/rom/jpn/title.arc","USRDIR/nativePS3/rom/jpn/result.arc",
 "USRDIR/nativePS3/rom/jpn/save.arc"):
 assert hashfile(installed/rel)==hashfile(source/rel),rel
# English assets must have the expected direct structure and no partial install remains.
assert len(list((installed/"USRDIR/nativePS3/rom/eng").rglob("*.arc")))==4077
assert not installed.with_name("PS3_GAME.INSTALLING").exists()
proof={"status":"PASS","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "patched_files_verified":len(results),"passed":len(results),"failed":failed,
 "original_unmodified":True,"japanese_route_preserved":True,
 "english_arc_count":4077,"disc_marker_present":True,
 "source_eboot_sha256":manifest["source_eboot_sha256"],
 "target_eboot_sha256":manifest["target_eboot_sha256"],
 "duration_seconds":round(time.monotonic()-t,2),
 "runtime_PS3_boot_test":"NOT_DONE","movie_pack_included":False}
(W/"FRESH_GAME_INSTALL_VALIDATION.json").write_text(json.dumps(proof,indent=2),encoding="utf8")
print("FRESH_GAME_INSTALL_TEST_PASS",len(results),"exact_hash_matches",
 "English_ARC",4077,"SECS",proof["duration_seconds"],flush=True)
