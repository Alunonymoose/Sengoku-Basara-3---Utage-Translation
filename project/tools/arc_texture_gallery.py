#!/usr/bin/env python3
"""
ARC Texture Gallery — BASARA Foundry

One-command visual QA for PS3 MT Framework Lite ARC v8 files.

Given an ARC path (absolute, relative to live rom/eng, or a unique ARC basename),
this tool:
  * validates/parses the ARC with safe_arc.py;
  * finds every XET/TEX resource and decodes it using xet_ps3.decode_display(),
    i.e. the game-faithful RGBA view (including 0x2A YCbCr shader conversion);
  * saves every texture as a full-resolution PNG;
  * makes compact overview sheets suitable for ChatGPT / human visual sweeps;
  * creates a browsable HTML gallery;
  * compares against the same Utage JPN ARC when available;
  * compares by resource basename against the Samurai Heroes donor index;
  * records artifact-oriented QA metrics in manifest.json.

This tool is READ-ONLY. It never patches an ARC.

Examples:
  python arc_texture_gallery.py title.arc
  python arc_texture_gallery.py select\\c_story.arc
  python arc_texture_gallery.py "E:\\Utage Patching New\\PS3_GAME\\USRDIR\\nativePS3\\rom\\eng\\versus\\menu.arc"
  python arc_texture_gallery.py title.arc --open
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import cv2
except Exception:
    cv2 = None

LIVE_ENG = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
LIVE_JPN = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
DEFAULT_OUTPUT = Path(r"E:\BASARA_WORK\ARC_TEXTURE_GALLERIES")
PROJECT = Path(__file__).resolve().parents[1]

SAFE_ARC_CANDIDATES = [
    PROJECT / r"tools\donor_matcher_v5_1_2026-09-23\safe_arc.py",
    Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\tools\donor_matcher_v5_1_2026-09-23\safe_arc.py"),
]
XET_CANDIDATES = [
    PROJECT / r"texture_tools\xet_ps3_2026-09-25\xet_ps3.py",
    Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25\xet_ps3.py"),
]
DONOR_INDEX_CANDIDATES = [
    PROJECT / r"Alrummi3\dist\donor_index.json",
    Path(r"E:\Utage Patching New\Alrummi3\dist\donor_index.json"),
]

XET_TYPE_HASH = 0x241F5DEB
CHECKER_A = (102, 102, 102)
CHECKER_B = (148, 148, 148)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_module(name: str, candidates: list[Path]):
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Unable to locate dependency {name}; tried: {candidates}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod, path


def resolve_arc(arg: str) -> Path:
    raw = Path(arg.strip('"'))
    if raw.exists():
        return raw.resolve()

    rel = Path(arg.replace("/", "\\"))
    candidate = LIVE_ENG / rel
    if candidate.exists():
        return candidate.resolve()

    # If no extension was supplied, try .arc.
    if rel.suffix.lower() != ".arc":
        candidate = LIVE_ENG / (str(rel) + ".arc")
        if candidate.exists():
            return candidate.resolve()

    # Unique basename search under live ENG.
    basename = rel.name
    if not basename.lower().endswith(".arc"):
        basename += ".arc"
    matches = [p for p in LIVE_ENG.rglob("*.arc") if p.name.lower() == basename.lower()]
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise FileNotFoundError(f"No ARC matching {arg!r} under {LIVE_ENG}")
    msg = "\n".join(f"  - {p}" for p in matches[:50])
    raise RuntimeError(f"ARC name is ambiguous ({len(matches)} matches):\n{msg}")


def jpn_counterpart(arc: Path) -> Path | None:
    try:
        rel = arc.resolve().relative_to(LIVE_ENG.resolve())
    except Exception:
        return None
    p = LIVE_JPN / rel
    return p if p.exists() else None


def safe_filename(s: str, maxlen: int = 110) -> str:
    s = s.replace("\\", "__").replace("/", "__")
    s = re.sub(r'[^A-Za-z0-9_.() -]+', "_", s)
    s = re.sub(r"\s+", "_", s).strip("._")
    if len(s) > maxlen:
        s = s[:maxlen]
    return s or "unnamed"


def checker(w: int, h: int, tile: int = 16) -> Image.Image:
    im = Image.new("RGB", (w, h), CHECKER_A)
    d = ImageDraw.Draw(im)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if (x // tile + y // tile) & 1:
                d.rectangle((x, y, min(w - 1, x + tile - 1), min(h - 1, y + tile - 1)), fill=CHECKER_B)
    return im


def component_metrics(alpha: np.ndarray) -> dict:
    mask = (alpha > 8).astype(np.uint8)
    if not mask.any():
        return {
            "component_count": 0,
            "tiny_components_le8": 0,
            "small_components_le24": 0,
            "largest_component_area": 0,
        }
    if cv2 is None:
        return {
            "component_count": None,
            "tiny_components_le8": None,
            "small_components_le24": None,
            "largest_component_area": None,
        }
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    areas = [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)]
    return {
        "component_count": len(areas),
        "tiny_components_le8": sum(a <= 8 for a in areas),
        "small_components_le24": sum(a <= 24 for a in areas),
        "largest_component_area": max(areas) if areas else 0,
    }


def visual_metrics(arr: np.ndarray) -> dict:
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 8)
    bbox = None if len(xs) == 0 else [
        int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    ]
    edge_alpha = int(
        (alpha[0, :] > 8).sum()
        + (alpha[-1, :] > 8).sum()
        + (alpha[:, 0] > 8).sum()
        + (alpha[:, -1] > 8).sum()
    )
    transparent = alpha == 0
    rgb_dirty = int((np.any(arr[..., :3] != 0, axis=2) & transparent).sum())
    semi = int(((alpha > 0) & (alpha < 255)).sum())
    opaque = int((alpha > 8).sum())
    out = {
        "alpha_bbox": bbox,
        "edge_alpha_pixels": edge_alpha,
        "transparent_rgb_nonzero_pixels": rgb_dirty,
        "semi_transparent_pixels": semi,
        "visible_alpha_pixels": opaque,
    }
    out.update(component_metrics(alpha))
    return out


def load_donor_index() -> tuple[dict | None, Path | None]:
    path = next((p for p in DONOR_INDEX_CANDIDATES if p.exists()), None)
    if path is None:
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except Exception:
        return None, path


def build_jpn_map(safe_arc, jpn: Path | None) -> tuple[list[dict] | None, dict]:
    if jpn is None:
        return None, {}
    try:
        entries = safe_arc.parse_arc(jpn.read_bytes())
    except Exception:
        return None, {}
    mp: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for e in entries:
        mp[(e["name"], e["type_hash"])].append(e)
    return entries, mp


def match_jpn(entry: dict, index: int, jpn_entries, jpn_map) -> dict:
    if jpn_entries is None:
        return {"available": False, "exact": None, "matched_by": None}
    candidates = jpn_map.get((entry["name"], entry["type_hash"]), [])
    if candidates:
        je = candidates[0]
        return {
            "available": True,
            "exact": je["raw"] == entry["raw"],
            "matched_by": "name+type",
            "jpn_index": je["index"],
            "jpn_raw_sha256": sha256_bytes(je["raw"]),
        }
    if index < len(jpn_entries) and jpn_entries[index]["type_hash"] == entry["type_hash"]:
        je = jpn_entries[index]
        return {
            "available": True,
            "exact": je["raw"] == entry["raw"],
            "matched_by": "index+type",
            "jpn_index": index,
            "jpn_raw_sha256": sha256_bytes(je["raw"]),
        }
    return {"available": True, "exact": None, "matched_by": None}


class DonorMatcher:
    def __init__(self, safe_arc, donor_index):
        self.safe_arc = safe_arc
        self.di = donor_index
        self.cache: dict[str, list[dict] | None] = {}

    @staticmethod
    def key_for(entry: dict) -> str:
        return entry["name"].rsplit("\\", 1)[-1].lower()

    def _arc_entries(self, path: str):
        if path in self.cache:
            return self.cache[path]
        try:
            p = Path(path)
            entries = self.safe_arc.parse_arc(p.read_bytes())
        except Exception:
            entries = None
        self.cache[path] = entries
        return entries

    def inspect(self, entry: dict, max_candidates: int = 20) -> dict:
        if not self.di:
            return {"available": False, "donor_count": 0, "exact": False, "exact_paths": [], "candidate_paths": []}
        key = self.key_for(entry)
        pairs = self.di.get("by_key", {}).get(key, [])
        archives = self.di.get("archives", [])
        exact_paths = []
        candidate_paths = []
        checked = 0
        for ai, mi in pairs:
            if checked >= max_candidates:
                break
            if ai >= len(archives):
                continue
            ap = archives[ai]
            checked += 1
            candidate_paths.append(ap)
            aes = self._arc_entries(ap)
            if aes is None or mi >= len(aes):
                continue
            de = aes[mi]
            if de["type_hash"] == entry["type_hash"] and de["raw"] == entry["raw"]:
                exact_paths.append(ap)
        return {
            "available": True,
            "donor_count": len(pairs),
            "checked": checked,
            "exact": bool(exact_paths),
            "exact_paths": exact_paths[:5],
            "candidate_paths": candidate_paths[:5],
        }


def priority_flags(jpn: dict, sh: dict, metrics: dict) -> tuple[int, list[str]]:
    score = 0
    flags: list[str] = []

    if jpn.get("exact") is True:
        flags.append("JPN_IDENTICAL")
        if not sh.get("exact"):
            score += 3
            flags.append("REVIEW_JPN_IDENTICAL")
    elif jpn.get("exact") is False:
        flags.append("DIFFERS_JPN")
        if not sh.get("exact"):
            score += 2
            flags.append("CUSTOM_OR_UTAGE")
    else:
        flags.append("NO_JPN_MATCH")
        score += 1

    if sh.get("exact"):
        flags.append("SH_ENG_EXACT")
        score = max(0, score - 2)
    elif sh.get("available") and sh.get("donor_count", 0):
        flags.append("SH_DONOR_EXISTS")

    if metrics["edge_alpha_pixels"] > 0:
        flags.append("EDGE_TOUCH")
        score += 1
    tc = metrics.get("tiny_components_le8")
    if isinstance(tc, int) and tc >= 5:
        flags.append("TINY_COMPONENTS")
        score += 1
    if metrics["transparent_rgb_nonzero_pixels"] > 0:
        flags.append("RGB_UNDER_ZERO_ALPHA")
        score += 1

    return score, flags


def make_sheet(items: list[dict], out: Path, title: str, cols: int = 5, per_sheet: int = 20) -> list[str]:
    if not items:
        return []
    font = ImageFont.load_default()
    thumb_w, thumb_h = 250, 205
    label_h = 62
    gap = 8
    paths = []
    total_sheets = math.ceil(len(items) / per_sheet)

    for si in range(total_sheets):
        subset = items[si * per_sheet:(si + 1) * per_sheet]
        rows = math.ceil(len(subset) / cols)
        header_h = 34
        W = cols * thumb_w + (cols + 1) * gap
        H = header_h + rows * (thumb_h + label_h) + (rows + 1) * gap
        sheet = Image.new("RGB", (W, H), (25, 25, 25))
        d = ImageDraw.Draw(sheet)
        d.text((gap, 9), f"{title}  [{si + 1}/{total_sheets}]", font=font, fill=(255, 255, 255))
        for j, item in enumerate(subset):
            rr, cc = divmod(j, cols)
            x = gap + cc * thumb_w
            y = header_h + gap + rr * (thumb_h + label_h)
            bg = checker(thumb_w, thumb_h, 14)
            im = Image.open(item["png_abs"]).convert("RGBA")
            q = im.copy()
            q.thumbnail((thumb_w - 8, thumb_h - 8), Image.Resampling.LANCZOS)
            bg.paste(q, ((thumb_w - q.width) // 2, (thumb_h - q.height) // 2), q)
            sheet.paste(bg, (x, y))
            base = item["basename"]
            if len(base) > 34:
                base = base[:31] + "..."
            edge = item["metrics"]["edge_alpha_pixels"]
            tiny = item["metrics"]["tiny_components_le8"]
            rgb0 = item["metrics"]["transparent_rgb_nonzero_pixels"]
            d.text((x, y + thumb_h + 2), f"#{item['index']:03d} {base}", font=font, fill=(255, 255, 255))
            d.text((x, y + thumb_h + 16), f"{item['width']}x{item['height']} f0x{item['format']:02X} | J:{item['jpn_status'][:4]} S:{item['sh_status'][:4]}", font=font, fill=(190, 225, 255))
            d.text((x, y + thumb_h + 30), f"priority {item['priority_score']} | edge {edge} | tiny {tiny}", font=font, fill=(255, 235, 150))
            d.text((x, y + thumb_h + 44), f"rgb-under-alpha0 {rgb0}", font=font, fill=(210, 210, 210))
        p = out.with_name(f"{out.stem}_{si + 1:02d}{out.suffix}")
        sheet.save(p)
        paths.append(str(p))
    return paths


def make_chat_book(items: list[dict], out: Path, title: str, cols: int = 4, per_page: int = 16) -> list[str]:
    """Large, readable contact-sheet pages designed to be displayed directly in ChatGPT."""
    if not items:
        return []

    def ui_font(size: int):
        for fp in (
            Path(r"C:\Windows\Fonts\segoeui.ttf"),
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\calibri.ttf"),
        ):
            if fp.exists():
                try:
                    return ImageFont.truetype(str(fp), size)
                except Exception:
                    pass
        return ImageFont.load_default()

    font = ui_font(17)
    small = ui_font(14)
    header_font = ui_font(22)
    thumb_w, thumb_h = 315, 260
    label_h = 76
    gap = 10
    header_h = 48
    paths = []
    total_pages = math.ceil(len(items) / per_page)

    for pi in range(total_pages):
        subset = items[pi * per_page:(pi + 1) * per_page]
        rows = math.ceil(len(subset) / cols)
        W = cols * thumb_w + (cols + 1) * gap
        H = header_h + rows * (thumb_h + label_h) + (rows + 1) * gap
        page = Image.new("RGB", (W, H), (24, 24, 24))
        d = ImageDraw.Draw(page)
        d.text((gap, 11), f"{title}   PAGE {pi + 1}/{total_pages}", font=header_font, fill=(255, 255, 255))

        for j, item in enumerate(subset):
            rr, cc = divmod(j, cols)
            x = gap + cc * thumb_w
            y = header_h + gap + rr * (thumb_h + label_h)

            bg = checker(thumb_w, thumb_h, 16)
            im = Image.open(item["png_abs"]).convert("RGBA")
            q = im.copy()
            q.thumbnail((thumb_w - 12, thumb_h - 12), Image.Resampling.LANCZOS)
            bg.paste(q, ((thumb_w - q.width) // 2, (thumb_h - q.height) // 2), q)
            page.paste(bg, (x, y))

            base = item["basename"]
            if len(base) > 36:
                base = base[:33] + "..."
            top_flags = ",".join(item["flags"][:2]) or "OK"

            d.text((x, y + thumb_h + 4), f"#{item['index']:03d}  {base}", font=font, fill=(255, 255, 255))
            d.text((x, y + thumb_h + 26),
                   f"{item['width']}x{item['height']}  J:{item['jpn_status']}  SH:{item['sh_status']}",
                   font=small, fill=(190, 225, 255))
            d.text((x, y + thumb_h + 47),
                   f"QA {item['priority_score']}  {top_flags}",
                   font=small, fill=(255, 231, 148))

        p = out.with_name(f"{out.stem}_{pi + 1:02d}{out.suffix}")
        page.save(p, optimize=True)
        paths.append(str(p))
    return paths


def write_html(items: list[dict], arc: Path, outdir: Path, manifest_rel: str) -> Path:
    cards = []
    for item in items:
        flags = " ".join(item["flags"])
        badge = " ".join(f"<span class='badge'>{html.escape(f)}</span>" for f in item["flags"])
        cards.append(f"""
        <article class="card" data-score="{item['priority_score']}" data-flags="{html.escape(flags)}" data-jpn="{item['jpn_status']}" data-sh="{item['sh_status']}">
          <a href="{html.escape(item['png_rel'])}" target="_blank">
            <div class="imgwrap"><img loading="lazy" src="{html.escape(item['png_rel'])}"></div>
          </a>
          <div class="meta">
            <div class="title">#{item['index']:03d} {html.escape(item['basename'])}</div>
            <div class="sub">{item['width']}×{item['height']} · fmt 0x{item['format']:02X} · mips {item['mips']} · score {item['priority_score']}</div>
            <div class="flags">{badge}</div>
            <div class="sub">JPN: {item['jpn_status']} · SH: {item['sh_status']}</div>
            <details><summary>internal / hashes</summary>
              <code>{html.escape(item['internal_name'])}</code><br>
              raw <code>{item['raw_sha256']}</code><br>
              alpha bbox <code>{html.escape(str(item['metrics']['alpha_bbox']))}</code><br>
              edge alpha <code>{item['metrics']['edge_alpha_pixels']}</code> · tiny≤8 <code>{item['metrics']['tiny_components_le8']}</code>
            </details>
          </div>
        </article>
        """)

    doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ARC Texture Gallery — {html.escape(arc.name)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 18px; background:#151515; color:#eee; }}
h1 {{ margin:0 0 5px; }}
.top {{ position:sticky; top:0; z-index:3; background:#151515ee; padding:8px 0 12px; }}
.controls button {{ margin:3px; padding:7px 10px; }}
.controls input {{ min-width:310px; padding:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(310px,1fr)); gap:12px; }}
.card {{ background:#242424; border:1px solid #3e3e3e; border-radius:8px; overflow:hidden; }}
.card.priority {{ border-color:#b89131; }}
.imgwrap {{ height:250px; display:flex; align-items:center; justify-content:center;
  background-color:#777;
  background-image:linear-gradient(45deg,#999 25%,transparent 25%),linear-gradient(-45deg,#999 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#999 75%),linear-gradient(-45deg,transparent 75%,#999 75%);
  background-size:24px 24px; background-position:0 0,0 12px,12px -12px,-12px 0px; }}
body.dark .imgwrap {{ background:#111; background-image:none; }}
body.light .imgwrap {{ background:#eee; background-image:none; }}
img {{ max-width:100%; max-height:100%; image-rendering:auto; }}
.meta {{ padding:10px; }}
.title {{ font-weight:700; word-break:break-word; }}
.sub {{ font-size:12px; color:#bbb; margin-top:4px; }}
.badge {{ display:inline-block; font-size:10px; background:#444; border-radius:4px; padding:2px 5px; margin:4px 4px 0 0; }}
code {{ font-size:11px; word-break:break-all; }}
a {{ color:#9dc7ff; }}
</style>
</head>
<body>
<div class="top">
<h1>ARC Texture Gallery</h1>
<div><b>{html.escape(str(arc))}</b></div>
<div>{len(items)} decoded game-view textures · <a href="{manifest_rel}">manifest.json</a></div>
<div class="controls">
<button onclick="filterMode('all')">All</button>
<button onclick="filterMode('priority')">QA priority</button>
<button onclick="filterMode('jpn')">JPN-identical</button>
<button onclick="filterMode('custom')">Custom / differs JPN</button>
<button onclick="filterMode('sh')">Official SH exact</button>
<button onclick="document.body.className=''">Checker</button>
<button onclick="document.body.className='dark'">Dark BG</button>
<button onclick="document.body.className='light'">Light BG</button>
<input id="q" placeholder="filter name / flag..." oninput="applyText()">
</div>
</div>
<div class="grid" id="grid">
{''.join(cards)}
</div>
<script>
let mode='all';
function show(c) {{
 const f=c.dataset.flags, j=c.dataset.jpn, sh=c.dataset.sh, score=+c.dataset.score;
 if(mode==='priority') return score>=2;
 if(mode==='jpn') return j==='exact';
 if(mode==='custom') return j==='different' || f.includes('CUSTOM_OR_UTAGE');
 if(mode==='sh') return sh==='exact';
 return true;
}}
function filterMode(m) {{ mode=m; applyText(); }}
function applyText() {{
 const q=document.getElementById('q').value.toLowerCase();
 document.querySelectorAll('.card').forEach(c => {{
   const ok=show(c) && (!q || c.innerText.toLowerCase().includes(q));
   c.style.display=ok?'':'none';
   c.classList.toggle('priority', +c.dataset.score>=2);
 }});
}}
applyText();
</script>
</body>
</html>"""
    p = outdir / "index.html"
    p.write_text(doc, encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="Decode and display every XET texture in an ARC.")
    ap.add_argument("arc", help="ARC path, rom/eng-relative path, or unique ARC basename")
    ap.add_argument("--out-root", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--open", action="store_true", help="Open index.html after generation")
    ap.add_argument("--no-sh", action="store_true", help="Skip Samurai Heroes donor-index comparison")
    ap.add_argument("--no-jpn", action="store_true", help="Skip corresponding Utage JPN ARC comparison")
    args = ap.parse_args()

    safe_arc, safe_path = load_module("arc_gallery_safe_arc", SAFE_ARC_CANDIDATES)
    xet, xet_path = load_module("arc_gallery_xet", XET_CANDIDATES)

    arc = resolve_arc(args.arc)
    data = arc.read_bytes()
    entries = safe_arc.parse_arc(data)

    jpn_path = None if args.no_jpn else jpn_counterpart(arc)
    jpn_entries, jpn_map = build_jpn_map(safe_arc, jpn_path)

    donor_index = None
    donor_index_path = None
    if not args.no_sh:
        donor_index, donor_index_path = load_donor_index()
    donors = DonorMatcher(safe_arc, donor_index)

    try:
        rel = arc.relative_to(LIVE_ENG)
        label = "__".join(rel.with_suffix("").parts)
    except Exception:
        label = safe_filename(arc.stem)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path(args.out_root) / f"{safe_filename(label)}__{stamp}"
    pngdir = outdir / "textures"
    sheetdir = outdir / "sheets"
    pngdir.mkdir(parents=True, exist_ok=True)
    sheetdir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    decode_failures = []
    raw_hash_groups: dict[str, list[int]] = defaultdict(list)

    for e in entries:
        if e["type_hash"] != XET_TYPE_HASH and not e["raw"].startswith(b"\x00XET"):
            continue
        try:
            inf = xet.info(e["raw"])
            arr = xet.decode_display(e["raw"])
            if arr.shape[:2] != (inf["height"], inf["width"]):
                raise ValueError(f"decoded shape {arr.shape} does not match header")
        except Exception as exc:
            decode_failures.append({
                "index": e["index"], "name": e["name"], "error": repr(exc)
            })
            continue

        rgba = np.asarray(arr, dtype=np.uint8)
        # Keep game display pixels exactly as decoder returned; zero RGB only for the saved
        # fully-transparent PNG pixels to make browser/checkerboard previews deterministic.
        save_rgba = rgba.copy()
        save_rgba[save_rgba[..., 3] == 0, :3] = 0

        base = e["name"].rsplit("\\", 1)[-1]
        pngname = f"{e['index']:04d}__{safe_filename(base)}.png"
        png_abs = pngdir / pngname
        Image.fromarray(save_rgba, "RGBA").save(png_abs)

        metrics = visual_metrics(rgba)
        jpn = match_jpn(e, e["index"], jpn_entries, jpn_map)
        sh = donors.inspect(e)

        score, flags = priority_flags(jpn, sh, metrics)
        rawsha = sha256_bytes(e["raw"])
        raw_hash_groups[rawsha].append(e["index"])

        jpn_status = (
            "exact" if jpn.get("exact") is True
            else "different" if jpn.get("exact") is False
            else "no-match" if jpn.get("available")
            else "unavailable"
        )
        sh_status = (
            "exact" if sh.get("exact")
            else "donor-found" if sh.get("donor_count", 0)
            else "no-donor" if sh.get("available")
            else "unavailable"
        )

        items.append({
            "index": e["index"],
            "internal_name": e["name"],
            "basename": base,
            "type_hash": f"0x{e['type_hash']:08X}",
            "width": int(inf["width"]),
            "height": int(inf["height"]),
            "mips": int(inf["mips"]),
            "format": int(inf["format"]),
            "codec": e["codec"],
            "warning": e["warning"],
            "raw_size": len(e["raw"]),
            "compressed_size": e["compressed_size"],
            "raw_sha256": rawsha,
            "stored_sha256": sha256_bytes(e["stored"]),
            "png_rel": f"textures/{pngname}",
            "png_abs": str(png_abs),
            "metrics": metrics,
            "jpn": jpn,
            "jpn_status": jpn_status,
            "samurai_heroes": sh,
            "sh_status": sh_status,
            "priority_score": int(score),
            "flags": flags,
        })

    # Duplicate payload hints.
    dup_groups = [v for v in raw_hash_groups.values() if len(v) > 1]
    dup_index_to_group = {}
    for group_id, grp in enumerate(dup_groups, 1):
        for idx in grp:
            dup_index_to_group[idx] = group_id
    for item in items:
        gid = dup_index_to_group.get(item["index"])
        if gid is not None:
            item["duplicate_group"] = gid
            item["flags"].append("DUPLICATE_RAW")
        else:
            item["duplicate_group"] = None

    items.sort(key=lambda x: x["index"])
    priority = sorted(items, key=lambda x: (-x["priority_score"], x["index"]))

    all_sheets = make_sheet(items, sheetdir / "overview.png", f"{arc.name} — ALL TEXTURES")
    chat_pages = make_chat_book(items, sheetdir / "chatbook.png", f"{arc.name} - IN-CHAT TEXTURE BOOK")
    texture_book_pdf = outdir / "TEXTURE_BOOK.pdf"
    if chat_pages:
        pdf_images = [Image.open(p).convert("RGB") for p in chat_pages]
        pdf_images[0].save(texture_book_pdf, save_all=True, append_images=pdf_images[1:], resolution=150.0)
        for _im in pdf_images:
            _im.close()
    else:
        texture_book_pdf = None
    priority_items = [x for x in priority if x["priority_score"] >= 2]
    priority_sheets = make_sheet(priority_items, sheetdir / "qa_priority.png", f"{arc.name} - QA PRIORITY")
    priority_chat_pages = make_chat_book(priority_items, sheetdir / "chatbook_suspects.png", f"{arc.name} - SUSPECTS")
    custom_items = [x for x in items if x["jpn_status"] == "different" and x["sh_status"] != "exact"]
    custom_sheets = make_sheet(custom_items, sheetdir / "custom_english.png", f"{arc.name} — CUSTOM / DIFFERS JPN")

    manifest = {
        "tool": "ARC Texture Gallery",
        "version": 1,
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "source_arc": str(arc),
        "source_arc_sha256": sha256_bytes(data),
        "source_arc_size": len(data),
        "arc_member_count": len(entries),
        "texture_count": len(items),
        "decode_failure_count": len(decode_failures),
        "decode_failures": decode_failures,
        "jpn_counterpart": str(jpn_path) if jpn_path else None,
        "samurai_heroes_donor_index": str(donor_index_path) if donor_index_path else None,
        "safe_arc_module": str(safe_path),
        "xet_module": str(xet_path),
        "overview_sheets": [str(Path(p).relative_to(outdir)).replace("\\", "/") for p in all_sheets],
        "chat_pages": [str(Path(p).relative_to(outdir)).replace("\\", "/") for p in chat_pages],
        "priority_sheets": [str(Path(p).relative_to(outdir)).replace("\\", "/") for p in priority_sheets],
        "priority_chat_pages": [str(Path(p).relative_to(outdir)).replace("\\", "/") for p in priority_chat_pages],
        "custom_sheets": [str(Path(p).relative_to(outdir)).replace("\\", "/") for p in custom_sheets],
        "texture_book_pdf": str(texture_book_pdf.relative_to(outdir)).replace("\\", "/") if texture_book_pdf else None,
        "summary": {
            "jpn_exact": sum(x["jpn_status"] == "exact" for x in items),
            "jpn_different": sum(x["jpn_status"] == "different" for x in items),
            "sh_exact": sum(x["sh_status"] == "exact" for x in items),
            "custom_or_utage": sum("CUSTOM_OR_UTAGE" in x["flags"] for x in items),
            "edge_touch": sum("EDGE_TOUCH" in x["flags"] for x in items),
            "tiny_component_flag": sum("TINY_COMPONENTS" in x["flags"] for x in items),
            "priority_ge2": sum(x["priority_score"] >= 2 for x in items),
            "duplicate_raw_groups": len(dup_groups),
        },
        "textures": items,
    }
    manifest_path = outdir / "manifest.json"
    # Remove local-only absolute PNG helper before writing manifest.
    manifest_public = json.loads(json.dumps(manifest))
    for x in manifest_public["textures"]:
        x.pop("png_abs", None)
    manifest_path.write_text(json.dumps(manifest_public, indent=2), encoding="utf-8")

    html_path = write_html(items, arc, outdir, "manifest.json")

    latest = {
        "generated": manifest["generated"],
        "arc": str(arc),
        "output_dir": str(outdir),
        "html": str(html_path),
        "overview_sheets": all_sheets,
        "chat_pages": chat_pages,
        "priority_sheets": priority_sheets,
        "priority_chat_pages": priority_chat_pages,
        "custom_sheets": custom_sheets,
        "texture_book_pdf": str(texture_book_pdf) if texture_book_pdf else None,
        "manifest": str(manifest_path),
    }
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    (DEFAULT_OUTPUT / "LATEST.json").write_text(json.dumps(latest, indent=2), encoding="utf-8")

    print("ARC_TEXTURE_GALLERY_OK")
    print(f"ARC={arc}")
    print(f"TEXTURES={len(items)}")
    print(f"DECODE_FAILURES={len(decode_failures)}")
    print(f"OUTPUT={outdir}")
    print(f"HTML={html_path}")
    if texture_book_pdf:
        print(f"PDF={texture_book_pdf}")
    print(f"MANIFEST={manifest_path}")
    for p in all_sheets:
        print(f"SHEET={p}")
    for p in priority_sheets:
        print(f"PRIORITY_SHEET={p}")
    for p in custom_sheets:
        print(f"CUSTOM_SHEET={p}")

    if args.open:
        try:
            os.startfile(str(html_path))
        except Exception as exc:
            print(f"OPEN_FAILED={exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
