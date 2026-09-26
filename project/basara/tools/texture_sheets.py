#!/usr/bin/env python3
"""Contact sheets of every language-keyed texture, for visual Japanese-text review.

Needs basara (pip install ".../project/basara"). Read-only on the game folders.

    python texture_sheets.py --eng "<rom\\eng>" --jpn "<rom\\jpn>" --out C:\\tex_review

For every ARC under --eng (backup copies skipped) it takes each XET member whose
internal name carries a language folder (\\jpn\\ or \\eng\\ -- the project's key for
localisable resources), decodes the top level in DISPLAY space, and compares the
raw member with the same archive/member under --jpn:

    SAME_AS_JPN   never localised (Japanese text would still be there)
    CHANGED       edited in the English build
    NO_JPN        no counterpart in rom/jpn

Identical payloads are stored once (with every owner listed). Output:
    texture_index.json         every texture: owners, format, size, status, tile id
    sheets/sheet_NNNN.jpg      6x5 labelled tiles: SAME_AS_JPN, then NO_JPN, then CHANGED
    review_partNN.zip          sheets + index, <= --max-mb each, ready to upload
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from basara import arc as arcmod
from basara import xet

SKIP = re.compile(r"backup|BACKUP|Copy|PRE_", re.I)
LANG_KEY = re.compile(r"\\(jpn|eng)\\", re.I)
TILE_W, TILE_H, COLS, ROWS = 300, 190, 6, 5


def members(root: Path):
    for p in sorted(root.rglob("*.arc")):
        rel = p.relative_to(root).as_posix()
        if SKIP.search(rel):
            continue
        try:
            a = arcmod.inspect(p.read_bytes())
        except (arcmod.ArcError, OSError) as exc:
            print(f"skip {rel}: {exc}", file=sys.stderr)
            continue
        for e in a:
            if LANG_KEY.search(e.name) and e.magic == xet.MAGIC:
                yield rel, e


def thumb(raw: bytes) -> Image.Image | None:
    try:
        img = Image.fromarray(xet.decode_display(raw), "RGBA")
    except Exception:
        return None
    bg = Image.new("RGBA", img.size, (48, 48, 56, 255))      # dark backing so white text shows
    bg.alpha_composite(img)
    k = min((TILE_W - 8) / bg.width, (TILE_H - 26) / bg.height)
    size = (max(1, int(bg.width * k)), max(1, int(bg.height * k)))
    bg = bg.resize(size, Image.NEAREST if k > 1 else Image.LANCZOS)   # small labels scale UP
    return bg.convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--jpn", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-mb", type=float, default=29.0)
    ap.add_argument("--skip-changed", action="store_true",
                    help="omit textures already edited in ENG (default: include them -- partly translated atlases can still hold Japanese)")
    a = ap.parse_args()
    eng, jpn, out = Path(a.eng), Path(a.jpn), Path(a.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)

    jpn_cache: dict[str, dict[str, str]] = {}

    def jpn_hash(rel: str, name: str) -> str | None:
        if rel not in jpn_cache:
            p = jpn / rel
            jpn_cache[rel] = {}
            if p.exists():
                try:
                    for e in arcmod.inspect(p.read_bytes()):
                        if e.magic == xet.MAGIC:
                            jpn_cache[rel][e.name] = hashlib.sha256(e.raw).hexdigest()
                except (arcmod.ArcError, OSError):
                    pass
        return jpn_cache[rel].get(name)

    uniq: dict[str, dict] = {}
    n = 0
    for rel, e in members(eng):
        raw = e.raw
        h = hashlib.sha256(raw).hexdigest()
        jh = jpn_hash(rel, e.name)
        status = "NO_JPN" if jh is None else "SAME_AS_JPN" if jh == h else "CHANGED"
        rec = uniq.get(h)
        if rec is None:
            try:
                info = xet.xet_info(raw)
                fmt, w, hgt = f"0x{info.format_code:02X}", info.width, info.height
            except Exception as exc:
                fmt, w, hgt = f"ERR {exc}", 0, 0
            rec = uniq[h] = {"sha256": h, "format": fmt, "width": w, "height": hgt, "status": status,
                             "name": e.name, "owners": [], "_raw": raw}
        rec["owners"].append({"arc": rel, "index": e.index, "status": status})
        if status == "SAME_AS_JPN":
            rec["status"] = "SAME_AS_JPN"          # worst case wins
        n += 1
        if n % 2000 == 0:
            print(f"{n} textures scanned, {len(uniq)} unique", flush=True)

    order = {"SAME_AS_JPN": 0, "NO_JPN": 1, "CHANGED": 2}
    todo = sorted((r for r in uniq.values() if not a.skip_changed or r["status"] != "CHANGED"),
                  key=lambda r: (order[r["status"]], r["name"]))
    per = COLS * ROWS
    sheets = []
    for s in range(0, len(todo), per):
        sheet = Image.new("RGB", (COLS * TILE_W, ROWS * TILE_H), (20, 20, 24))
        d = ImageDraw.Draw(sheet)
        for k, rec in enumerate(todo[s:s + per]):
            tid = s + k
            rec["tile"] = tid
            x, y = (k % COLS) * TILE_W, (k // COLS) * TILE_H
            t = thumb(rec["_raw"])
            if t is not None:
                sheet.paste(t, (x + 4, y + 22))
            d.text((x + 4, y + 4), f"#{tid} {rec['status'][:4]} {rec['width']}x{rec['height']} {rec['name'].split(chr(92))[-1][:26]}",
                   fill=(255, 230, 120))
        p = out / "sheets" / f"sheet_{s // per:04}.jpg"
        sheet.save(p, quality=82)
        sheets.append(p)
    index = [{k: v for k, v in r.items() if k != "_raw"} for r in uniq.values()]
    (out / "texture_index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")

    limit, part, zf = int(a.max_mb * 1024 * 1024), 0, None
    def new_part():
        nonlocal part, zf
        if zf:
            zf.close()
        part += 1
        zf = zipfile.ZipFile(out / f"review_part{part:02}.zip", "w", zipfile.ZIP_DEFLATED)
    new_part()
    zf.write(out / "texture_index.json", "texture_index.json")
    for p in sheets:
        if (out / f"review_part{part:02}.zip").stat().st_size + p.stat().st_size > limit - 65536:
            new_part()
        zf.write(p, f"sheets/{p.name}")
    zf.close()
    counts = {}
    for r in uniq.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"done: {n} language-keyed textures, {len(uniq)} unique {counts}; {len(todo)} tiles on {len(sheets)} sheets; {part} upload part(s)")
    for p in sorted(out.glob("review_part*.zip")):
        print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
