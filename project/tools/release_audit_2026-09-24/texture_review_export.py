#!/usr/bin/env python3
"""
BASARA Foundry texture visual-review exporter.
Read-only: extracts/decodes current live rTextures and writes deduplicated PNG
previews + HTML/JSON review index outside the game root.

0x15 is decoded read-only as fixture-proven DXT3/BC2. No writer claim is made here.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

R_TEXTURE = 0x241F5DEB
EXPECTED_SAFE_ARC_SHA256 = "f25c53e4ad78e18d5785b8aee197725377130ed9f562a9caa1000a1964bde91d"
EXPECTED_XET_DECODER_SHA256 = "d82376add94be9f0c132590d150936d91fd6241d76b04723d88ec3ae4ced4738"

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
SAFE_ARC_PATH = TOOLS_DIR / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
XET_DECODER_PATH = TOOLS_DIR.parent / "texture_tools" / "xet_recovery_2026-09-23" / "foundry_xet_decoder_20260923.py"

TEXT_HINTS = (
    "name", "title", "waza", "menu", "brief", "tenka", "roulette", "cockpit",
    "gallery", "panel", "wep", "shop", "item", "skill", "command", "caption",
    "rule", "rank", "result", "select", "story", "mode", "history", "logo",
    "cp_", "teki_", "local", "goods", "weapon", "versus", "unification",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing dependency: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"dependency hash drift: {path} expected={expected} actual={actual}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(f"RGBA length {len(rgba)} != expected {expected}")
    scan = bytearray()
    stride = width * 4
    for y in range(height):
        scan.append(0)  # PNG filter: None
        scan.extend(rgba[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(scan), 9))
        + _png_chunk(b"IEND", b"")
    )


def likely_text(path: str) -> bool:
    low = path.lower()
    return any(h in low for h in TEXT_HINTS)


def stable_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> int:
    ap = argparse.ArgumentParser(description="Export deduplicated current-live XET previews for human review")
    ap.add_argument("live_root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--likely-text-only", action="store_true",
                    help="Fast review subset by resource-name hints; never counts as full release census.")
    args = ap.parse_args()

    root = args.live_root.resolve()
    out = args.out.resolve()
    if not root.is_dir():
        print(f"invalid live root: {root}", file=sys.stderr)
        return 3
    if out == root or out.is_relative_to(root):
        print("--out must be outside live root", file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)
    img_dir = out / "images"
    img_dir.mkdir(exist_ok=True)

    try:
        require_hash(SAFE_ARC_PATH, EXPECTED_SAFE_ARC_SHA256)
        require_hash(XET_DECODER_PATH, EXPECTED_XET_DECODER_SHA256)
        safe_arc = load_module("basara_review_safe_arc", SAFE_ARC_PATH)
        xet = load_module("basara_review_xet", XET_DECODER_PATH)
    except Exception as exc:
        print(f"dependency failure: {exc}", file=sys.stderr)
        return 2

    groups: dict[str, dict[str, Any]] = {}
    quarantined = []
    errors = []
    providers_seen = 0
    providers_selected = 0

    for arc in sorted(root.rglob("*.arc")):
        rel_arc = stable_rel(arc, root)
        try:
            entries = safe_arc.parse_arc(arc.read_bytes())
        except Exception as exc:
            errors.append({"arc": rel_arc, "error": repr(exc)})
            continue

        for e in entries:
            if e["type_hash"] != R_TEXTURE:
                continue
            providers_seen += 1
            resource = e["name"]
            if args.likely_text_only and not likely_text(resource):
                continue
            providers_selected += 1
            raw = e["raw"]
            owner = {
                "arc": rel_arc,
                "member_index": e["index"],
                "resource": resource,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }
            try:
                info = xet.xet_info(raw)
                owner.update({
                    "width": info.width,
                    "height": info.height,
                    "mips": info.mip_count,
                    "format": f"0x{info.format_id:02X}",
                })
                xet.validate(raw)
                rgba = xet.decode_rgba(raw, 0)
                decoded_hash = hashlib.sha256(rgba).hexdigest()
                png_name = f"{decoded_hash[:24]}_{info.width}x{info.height}.png"
                png_path = img_dir / png_name
                if not png_path.exists():
                    png_path.write_bytes(rgba_png(info.width, info.height, rgba))

                g = groups.setdefault(decoded_hash, {
                    "decoded_rgba_sha256": decoded_hash,
                    "png": f"images/{png_name}",
                    "width": info.width,
                    "height": info.height,
                    "format": f"0x{info.format_id:02X}",
                    "mips": info.mip_count,
                    "likely_text": False,
                    "providers": [],
                    "review_state": "NEEDS_REVIEW",
                    "classification": None,
                    "notes": None,
                })
                g["likely_text"] = g["likely_text"] or likely_text(resource)
                g["providers"].append(owner)
            except Exception as exc:
                errors.append({
                    **owner,
                    "error": repr(exc),
                })

    ordered = sorted(
        groups.values(),
        key=lambda g: (not g["likely_text"], -len(g["providers"]), g["providers"][0]["resource"].lower())
    )

    payload = {
        "schema": "BASARA_FOUNDRY_TEXTURE_VISUAL_REVIEW_V1",
        "live_root_hint": str(root),
        "mode": "LIKELY_TEXT_SUBSET" if args.likely_text_only else "FULL_TEXTURE_SET",
        "warning": "Resource-name hinting is convenience only and cannot prove localisation completeness.",
        "providers_seen": providers_seen,
        "providers_selected": providers_selected,
        "unique_decoded_images": len(ordered),
        "quarantined_0x15": quarantined,
        "xet_0x15_read_policy": "fixture-proven DXT3/BC2 preview; production writing remains fail-closed",
        "errors": errors,
        "groups": ordered,
    }
    (out / "TEXTURE_REVIEW_INDEX.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cards = []
    for i, g in enumerate(ordered, 1):
        providers = "<br>".join(
            html.escape(f"{p['resource']} — {p['arc']} #{p['member_index']}")
            for p in g["providers"][:20]
        )
        if len(g["providers"]) > 20:
            providers += f"<br>… +{len(g['providers']) - 20} more providers"
        cards.append(f"""
<section>
  <h2>{i}. {html.escape(g['providers'][0]['resource'])}</h2>
  <img src="{html.escape(g['png'])}" loading="lazy">
  <p><b>{g['width']}×{g['height']}</b> · {html.escape(g['format'])} ·
     providers={len(g['providers'])} · likely_text={str(g['likely_text']).lower()}</p>
  <details><summary>Providers</summary>{providers}</details>
  <p>Review: □ English □ Japanese □ Mixed □ Neutral/effect □ Font atlas □ Needs context</p>
</section>""")

    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>BASARA Foundry Texture Review</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:20px}}
section{{border-bottom:1px solid #aaa;padding:20px 0}}
img{{max-width:100%;image-rendering:auto;background:#777}}
code{{word-break:break-all}}
</style>
<h1>BASARA Foundry Texture Review</h1>
<p>Mode: {payload['mode']} · unique images: {len(ordered)} · selected providers:
{providers_selected}/{providers_seen} · 0x15 quarantined: {len(quarantined)} · errors: {len(errors)}</p>
<p><b>Important:</b> identical decoded artwork is shown once and all providers are listed beneath it.
Classification is human/context review; path/hash equality is not language authority.</p>
{''.join(cards)}
"""
    (out / "index.html").write_text(doc, encoding="utf-8")

    print(json.dumps({
        "providers_seen": providers_seen,
        "providers_selected": providers_selected,
        "unique_decoded_images": len(ordered),
        "quarantined_0x15": len(quarantined),
        "errors": len(errors),
        "out": str(out),
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
