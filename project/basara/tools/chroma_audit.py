#!/usr/bin/env python3
"""Whole-game audit of edited 0x2A (YCbCr) textures, with deterministic repairs for the missing-prefill fault.

Needs basara (pip install ".../project/basara"). Read-only on the game folders.

    python chroma_audit.py --eng "<rom\\eng>" --jpn "<rom\\jpn>" --out C:\\chroma_audit

Every 0x2A texture whose ENG bytes differ from JPN (language-keyed names by default,
--all for every texture) is decoded in storage space and classified:

  OK                 chroma behaves like the JPN art
  MISSING_PREFILL    solid (alpha >= 240) texels are achromatic (>= 93% neutral), but fully transparent texels
                     were stored off-neutral (e.g. 0,0,0,0), so BC3 block endpoints drag the
                     edges off 123 -> magenta/green fringes in game (the waza2 fault).
                     REPAIRED here: luma + alpha kept, chroma set to 123, re-encoded with the
                     certified writer (prefill=dilate). Needs approval of the board before install.
  OPAQUE_CANVAS      JPN is mostly transparent, ENG is a solid coloured block (text drawn on a
                     coloured canvas; result_id labels). Needs new art, not a codec repair.
  SWAPPED_ENDPOINTS  byte-order evidence says the legacy xetenc writer.
  OFF_NEUTRAL        chroma far from the JPN art for another reason (review by eye).

Output (identical payloads handled once, every owner listed):
    audit.json                 every texture: owners, class, metrics, repair sha256
    REPAIR.tsv                 rows for tools/replace_members.py (only MISSING_PREFILL repairs)
    files/<sha16>.tex          the repaired bytes REPAIR.tsv points at
    boards/*.jpg               before | after for repairs; JPN | ENG for the other flagged classes
    upload_partNN.zip          boards + audit.json + REPAIR.tsv (<= --max-mb each) to send for approval

After the boards are approved:
    python replace_members.py --eng "<rom\\eng>" --list C:\\chroma_audit\\REPAIR.tsv --files C:\\chroma_audit\\files --out C:\\chroma_audit\\in
    basara build C:\\chroma_audit\\in\\patchset.toml --root "<rom\\eng>" --out C:\\chroma_audit\\build
    basara install C:\\chroma_audit\\build --root "<rom\\eng>" --backup-root E:\\BASARA_BACKUPS
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from basara import arc as arcmod
from basara import xet

SKIP = re.compile(r"backup|Copy|PRE_|alrummi3", re.I)
LANG_KEY = re.compile(r"\\(jpn|eng)\\", re.I)
N = 123


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _counterpart(ja, e):
    if ja is None:
        return None
    if e.index < len(ja.entries) and ja.entries[e.index].name.lower() == e.name.lower():
        return ja.entries[e.index]
    hits = [j for j in ja.entries if j.name.lower() == e.name.lower()]
    return hits[0] if len(hits) == 1 else None


def metrics(raw: bytes) -> dict:
    s = xet.decode_storage(raw).reshape(-1, 4).astype(int)
    a = s[:, 1]
    neutral = (np.abs(s[:, 0] - N) <= 12) & (np.abs(s[:, 2] - N) <= 12)
    cov, solid, hidden = a > 16, a >= 240, a <= 16
    share = lambda m, sel: round(float(m[sel].mean()), 4) if sel.any() else None
    return {"covered": round(float(cov.mean()), 4), "hidden": round(float(hidden.mean()), 4),
            "neutral_covered": share(neutral, cov), "neutral_solid": share(neutral, solid),
            "neutral_hidden": share(neutral, hidden),
            "chroma_median_covered": [int(np.median(s[cov, 0])), int(np.median(s[cov, 2]))] if cov.any() else None}


def classify(eng: bytes, jpn: bytes) -> tuple[str, dict]:
    me, mj = metrics(eng), metrics(jpn)
    ev = {"eng": me, "jpn": mj, "byte_order": xet.byte_order_evidence(eng).get("verdict")}
    if ev["byte_order"] == "swapped":
        return "SWAPPED_ENDPOINTS", ev
    if (mj["hidden"] or 0) >= 0.3 and me["hidden"] < 0.02 and (me["neutral_covered"] or 1) < 0.5:
        return "OPAQUE_CANVAS", ev
    nc, ns, nh = me["neutral_covered"], me["neutral_solid"], me["neutral_hidden"]
    if nc is None or nc >= 0.9 or (mj["neutral_covered"] is not None and nc >= mj["neutral_covered"] - 0.05):
        return "OK", ev
    if ns is not None and ns >= 0.93 and nh is not None and nh < 0.5:
        return "MISSING_PREFILL", ev
    return "OFF_NEUTRAL", ev


def repair_neutral(raw: bytes) -> tuple[bytes, dict]:
    st = xet.decode_storage(raw)
    y, a = st[..., 3], st[..., 1]
    new, _ = xet.graft(raw, np.dstack([y, y, y, a]).astype(np.uint8), prefill="dilate")
    s2 = xet.decode_storage(new).astype(int)
    cov = s2[..., 1] > 16
    i, j = xet.xet_info(raw), xet.xet_info(new)
    if (i.width, i.height, i.format_code, i.mip_count) != (j.width, j.height, j.format_code, j.mip_count) \
            or new[:i.mip_offsets[0]] != raw[:i.mip_offsets[0]]:
        raise xet.XetError("repair changed the resource shape or header")
    dy = np.abs(s2[..., 3] - y.astype(int))[cov]
    check = {"neutral_after": round(float(((np.abs(s2[..., 0] - N) <= 12) & (np.abs(s2[..., 2] - N) <= 12))[cov].mean()), 4)
             if cov.any() else 1.0,
             "luma_err_mean": round(float(dy.mean()), 3) if len(dy) else 0.0, "luma_err_max": int(dy.max()) if len(dy) else 0,
             "alpha_err_max": int(np.abs(s2[..., 1] - a.astype(int)).max())}
    return new, check


def _tile(raw: bytes, w: int = 380, h: int = 230) -> Image.Image:
    img = Image.fromarray(xet.decode_display(raw), "RGBA")
    bg = Image.new("RGBA", img.size, (30, 30, 36, 255))
    bg.alpha_composite(img)
    k = min(w / bg.width, h / bg.height)
    size = (max(1, int(bg.width * k)), max(1, int(bg.height * k)))
    return bg.resize(size, Image.NEAREST if k >= 1 else Image.LANCZOS).convert("RGB")


def boards(pairs, title_l: str, title_r: str, out: Path, stem: str, per: int = 8) -> list[Path]:
    files = []
    for s in range(0, len(pairs), per):
        chunk = pairs[s:s + per]
        sheet = Image.new("RGB", (2 * 390 + 20, 30 + len(chunk) * 262), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        d.text((10, 8), title_l, fill=(255, 200, 120))
        d.text((410, 8), title_r, fill=(140, 255, 160))
        for k, (label, left, right) in enumerate(chunk):
            y = 30 + k * 262
            d.text((10, y + 2), label, fill=(225, 225, 225))
            sheet.paste(_tile(left), (10, y + 22))
            sheet.paste(_tile(right), (410, y + 22))
        p = out / f"{stem}_{s // per + 1:03}.jpg"
        sheet.save(p, quality=88)
        files.append(p)
    return files


def run(eng: Path, jpn: Path, out: Path, all_textures: bool = False, max_mb: float = 29.0, log=print) -> dict:
    (out / "files").mkdir(parents=True, exist_ok=True)
    (out / "boards").mkdir(parents=True, exist_ok=True)
    uniq: dict[str, dict] = {}
    n_arc = 0
    for p in sorted(eng.rglob("*.arc")):
        rel = p.relative_to(eng).as_posix()
        if SKIP.search(rel) or not (jpn / rel).exists():
            continue
        try:
            ea, ja = arcmod.inspect(p.read_bytes()), arcmod.inspect((jpn / rel).read_bytes())
        except (arcmod.ArcError, OSError) as exc:
            log(f"skip {rel}: {exc}")
            continue
        n_arc += 1
        if n_arc % 1000 == 0:
            log(f"{n_arc} archives, {len(uniq)} edited 0x2A textures")
        for e in ea.entries:
            if e.magic != xet.MAGIC or not (all_textures or LANG_KEY.search(e.name)):
                continue
            j = _counterpart(ja, e)
            if j is None or j.magic != xet.MAGIC:
                continue
            raw = e.raw
            h = sha(raw)
            rec = uniq.get(h)
            if rec is None:
                jr = j.raw
                if jr == raw:
                    continue
                try:
                    info, jinfo = xet.xet_info(raw), xet.xet_info(jr)
                    if info.format_code != 0x2A or (info.width, info.height) != (jinfo.width, jinfo.height):
                        continue
                    cls, ev = classify(raw, jr)
                except Exception as exc:                          # unreadable: report, never repair
                    cls, ev = "UNREADABLE", {"error": str(exc)}
                rec = uniq[h] = {"sha256": h, "name": e.name, "class": cls, "evidence": ev, "owners": [],
                                 "_raw": raw, "_jpn": jr}
            rec["owners"].append(f"{rel}#{e.index}")
    rows, rep_pairs, flag_pairs = [], [], []
    for h, rec in sorted(uniq.items(), key=lambda kv: kv[1]["name"]):
        short = rec["name"].split("\\")[-1]
        if rec["class"] == "MISSING_PREFILL":
            try:
                new, check = repair_neutral(rec["_raw"])
            except xet.XetError as exc:
                rec["class"], rec["repair_error"] = "OFF_NEUTRAL", str(exc)
                continue
            nh = sha(new)
            (out / "files" / f"{nh[:16]}.tex").write_bytes(new)
            rec["repair"] = {"after_sha256": nh, **check}
            rep_pairs.append((f"{short}  ({len(rec['owners'])} owner(s))", rec["_raw"], new))
            for o in rec["owners"]:
                a, i = o.rsplit("#", 1)
                rows.append((a, i, rec["name"], h, f"{nh[:16]}.tex", nh))
        elif rec["class"] not in ("OK",):
            flag_pairs.append((f"{rec['class']}  {short}", rec["_jpn"], rec["_raw"]))
    with open(out / "REPAIR.tsv", "w", encoding="utf-8") as f:
        f.write("arc\tindex\tmember\tbefore_sha256\tfile\tafter_sha256\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    sheets = boards(rep_pairs, "BEFORE (live ENG)", "AFTER (repaired bytes)", out / "boards", "repair")
    sheets += boards(flag_pairs, "JPN original", "live ENG (flagged)", out / "boards", "flagged")
    audit = [{k: v for k, v in r.items() if not k.startswith("_")} for r in uniq.values()]
    (out / "audit.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
    limit, part, zf = int(max_mb * 1024 * 1024), 0, None

    def new_part():
        nonlocal part, zf
        if zf:
            zf.close()
        part += 1
        zf = zipfile.ZipFile(out / f"upload_part{part:02}.zip", "w", zipfile.ZIP_DEFLATED)
    new_part()
    zf.write(out / "audit.json", "audit.json")
    zf.write(out / "REPAIR.tsv", "REPAIR.tsv")
    for p in sheets:
        if (out / f"upload_part{part:02}.zip").stat().st_size + p.stat().st_size > limit - 65536:
            new_part()
        zf.write(p, f"boards/{p.name}")
    zf.close()
    counts: dict[str, int] = {}
    for r in uniq.values():
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    return {"edited_0x2A": len(uniq), "classes": counts, "repair_rows": len(rows), "upload_parts": part}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--jpn", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--all", action="store_true", help="every XET, not only \\jpn\\ / \\eng\\ names")
    ap.add_argument("--max-mb", type=float, default=29.0)
    a = ap.parse_args()
    eng, out = Path(a.eng), Path(a.out)
    if out.resolve() == eng.resolve() or eng.resolve() in out.resolve().parents:
        print("--out must be outside the live rom/eng tree", file=sys.stderr)
        return 2
    res = run(eng, Path(a.jpn), out, a.all, a.max_mb, log=lambda m: print(m, flush=True))
    print(f"done: {res}")
    for p in sorted(out.glob("upload_part*.zip")):
        print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
