from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

GALLERY = Path(r"E:\BASARA_FOUNDRY_ORCHESTRATION\project\tools\arc_texture_gallery.py")
LATEST = Path(r"E:\BASARA_WORK\ARC_TEXTURE_GALLERIES\LATEST.json")
OUTROOT = Path(r"E:\BASARA_WORK\CHAT_TEXTURE_HANDOFFS")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._") or "selection"

def load_latest() -> dict:
    return json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}

def ensure_gallery(arc: str, refresh: bool) -> dict:
    latest = load_latest()
    wanted = arc.lower().replace("/", "\\")
    current = str(latest.get("arc", "")).lower()
    reusable = (not refresh and current and (current.endswith(wanted) or Path(current).name == Path(wanted).name))
    if not reusable:
        subprocess.run([sys.executable, str(GALLERY), arc], check=True)
        latest = load_latest()
    return latest

def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare exact decoded ARC textures for chat handoff.")
    ap.add_argument("arc", help="ARC path, ENG-relative path, or unique basename")
    ap.add_argument("--match", required=True, help="Case-insensitive filename substring, e.g. tenka_rule")
    ap.add_argument("--refresh", action="store_true", help="Force a fresh gallery decode")
    args = ap.parse_args()

    latest = ensure_gallery(args.arc, args.refresh)
    gallery_dir = Path(latest["output_dir"])
    texture_dir = gallery_dir / "textures"
    hits = sorted(p for p in texture_dir.glob("*.png") if args.match.lower() in p.name.lower())
    if not hits:
        raise SystemExit(f"No decoded PNGs matching {args.match!r} in {texture_dir}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    handoff = OUTROOT / f"{safe_name(Path(latest['arc']).stem)}__{safe_name(args.match)}__{stamp}"
    handoff.mkdir(parents=True, exist_ok=False)
    files = []
    for src in hits:
        canonical = src.name.split("__", 1)[1] if "__" in src.name else src.name
        dst = handoff / canonical
        shutil.copy2(src, dst)
        files.append({"name": canonical, "path": str(dst), "sha256": sha256(dst), "bytes": dst.stat().st_size})

    manifest = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "source_arc": latest["arc"],
        "gallery_dir": str(gallery_dir),
        "match": args.match,
        "count": len(files),
        "files": files,
    }
    (handoff / "handoff.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    zip_path = Path(str(handoff) + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in files:
            zf.write(item["path"], arcname=item["name"])
        zf.write(handoff / "handoff.json", arcname="handoff.json")

    latest_handoff = {**manifest, "handoff_dir": str(handoff), "zip": str(zip_path)}
    OUTROOT.mkdir(parents=True, exist_ok=True)
    (OUTROOT / "LATEST.json").write_text(json.dumps(latest_handoff, indent=2), encoding="utf-8")

    print("CHAT_TEXTURE_HANDOFF_OK")
    print(f"SOURCE_ARC={latest['arc']}")
    print(f"HANDOFF_DIR={handoff}")
    print(f"ZIP={zip_path}")
    for item in files:
        print(f"FILE={item['path']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
