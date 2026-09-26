#!/usr/bin/env python3
"""Deterministic English label candidates on a copy of a real decoded texture.

    python label_candidates.py SPEC.json --out DIR

SPEC: {"texture": "<live member .tex>", "reference": "<JPN .tex, optional>", "name": "tenka_009",
       "edits": [{"rect": [x0, y0, x1, y1],         # the proven edit region (texture pixels)
                  "clear": "interp" | "transparent" | "text",   # how the Japanese is removed
                  "text_pred": "light" | "dark" | "red" | "light_or_red" | "not_red" | "any", # for clear == "text"
                  "text": "10% OFF", "font": "<ttf>", "size": 22 (max; shrinks to fit),
                  "fill": [r,g,b], "outline": [r,g,b], "outline_w": 2, "skew": 0.2,
                  "rotate": 0, "align": "center"}],
       "allow_inconclusive_byte_order": false}  # only for synthetic/flat textures

clear = interp       every row inside the rect is rebuilt by linear interpolation between the
                     pixels just outside its left and right edges (plates, gradients);
        transparent  the rect becomes fully transparent;
        text         only pixels matching text_pred are replaced by the median of the other
                     pixels in the rect (stamps, fans, textured plates).
Only pixels inside the union of the rects may change; that is checked, and the candidate is
refused otherwise. The candidate is grafted with the certified writer inside the mask; blocks
outside it stay byte-identical. Output: <name>.candidate.png, <name>.mask.png, <name>.tex,
<name>.board.png (reference | live | candidate) and <name>.json (hashes, rects,
unchanged_outside_mask). Approval of the board comes before any install (replace_members.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from basara import xet


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


PRED = {
    "light": lambda p: (p[..., 3] > 60) & (p[..., :3].min(-1) > 150),
    "dark": lambda p: (p[..., 3] > 60) & (p[..., :3].max(-1) < 90),
    "red": lambda p: (p[..., 3] > 60) & (p[..., 0] > 150) & (p[..., 1] < 120),
    "any": lambda p: p[..., 3] > 60,
    "light_or_red": lambda p: (p[..., 3] > 60) & ((p[..., :3].min(-1) > 170) | ((p[..., 0] > 190) & (p[..., 1] < 100))),
    "not_red": lambda p: (p[..., 3] > 60) & ~((p[..., 0] > 90) & (p[..., 1] < 70) & (p[..., 2] < 70)),
}


def _clear(img: np.ndarray, rect, mode: str, pred: str) -> None:
    x0, y0, x1, y1 = rect
    if mode == "transparent":
        img[y0:y1, x0:x1] = 0
    elif mode == "interp":
        left = img[y0:y1, max(x0 - 2, 0)].astype(float)
        right = img[y0:y1, min(x1 + 1, img.shape[1] - 1)].astype(float)
        t = np.linspace(0, 1, x1 - x0)[None, :, None]
        img[y0:y1, x0:x1] = np.rint(left[:, None, :] * (1 - t) + right[:, None, :] * t).astype(np.uint8)
    elif mode == "text":
        sub = img[y0:y1, x0:x1]
        m = PRED[pred](sub.astype(int))
        # grow the text mask by one pixel so anti-aliased edges go too
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        keep = sub[~g & (sub[..., 3] > 60)]
        fill = np.median(keep, axis=0).astype(np.uint8) if len(keep) else np.zeros(4, np.uint8)
        sub[g] = fill
    else:
        raise ValueError(f"unknown clear mode {mode}")


def _text_layer(size_wh, e) -> Image.Image:
    w, h = size_wh
    text = e.get("text", "")
    layer = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    if not text:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ow = int(e.get("outline_w", 2))
    size = int(e.get("size", h))
    while size > 6:
        font = ImageFont.truetype(e["font"], size * 4)
        x_l, t, r, b = ImageDraw.Draw(layer).textbbox((0, 0), text, font=font, stroke_width=ow * 4)
        skew_extra = abs(e.get("skew", 0)) * (b - t)
        if (r - x_l + skew_extra) <= w * 4 * 0.94 and (b - t) <= h * 4 * 0.9:
            break
        size -= 1
    d = ImageDraw.Draw(layer)
    tw, th = r - x_l, b - t
    x = (w * 4 - tw) / 2 - x_l if e.get("align", "center") == "center" else -x_l + 2
    y = (h * 4 - th) / 2 - t
    d.text((x, y), text, font=font, fill=tuple(e.get("fill", [255, 255, 255])) + (255,),
           stroke_width=ow * 4, stroke_fill=tuple(e.get("outline", [0, 0, 0])) + (255,))
    if e.get("skew"):
        k = e["skew"]
        layer = layer.transform(layer.size, Image.AFFINE, (1, k, -k * layer.size[1] / 2, 0, 1, 0), Image.BICUBIC)
    if e.get("rotate"):
        layer = layer.rotate(e["rotate"], Image.BICUBIC)
    return layer.resize((w, h), Image.LANCZOS)


def build(spec: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    raw = Path(spec["texture"]).read_bytes()
    live = xet.decode_display(raw)
    cand = live.copy()
    mask = np.zeros(live.shape[:2], bool)
    for e in spec["edits"]:
        x0, y0, x1, y1 = e["rect"]
        mask[y0:y1, x0:x1] = True
        _clear(cand, e["rect"], e.get("clear", "interp"), e.get("text_pred", "light"))
        lay = _text_layer((x1 - x0, y1 - y0), e)
        base = Image.fromarray(cand[y0:y1, x0:x1], "RGBA")
        base.alpha_composite(lay)
        cand[y0:y1, x0:x1] = np.array(base)
    outside_same = bool((cand[~mask] == live[~mask]).all())
    if not outside_same:
        raise SystemExit("candidate changed pixels outside the edit mask")
    name = spec["name"]
    Image.fromarray(cand, "RGBA").save(out / f"{name}.candidate.png")
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(out / f"{name}.mask.png")
    new, rep = xet.graft(raw, cand, mask=mask, prefill="dilate",
                         allow_inconclusive_byte_order=bool(spec.get("allow_inconclusive_byte_order")))
    (out / f"{name}.tex").write_bytes(new)
    final = xet.decode_display(new)
    # board: reference | live | final (decoded from the encoded bytes)
    panels = []
    if spec.get("reference"):
        panels.append(xet.decode_display(Path(spec["reference"]).read_bytes()))
    panels += [live, final]
    h, w = live.shape[:2]
    k = max(1, min(3, 1400 // w))
    board = Image.new("RGB", (w * k + 20, len(panels) * (h * k + 26) + 6), (14, 14, 18))
    dr = ImageDraw.Draw(board)
    labels = (["JPN reference"] if spec.get("reference") else []) + ["live ENG now", "CANDIDATE (decoded from the encoded bytes)"]
    for i, (p, lab) in enumerate(zip(panels, labels, strict=True)):
        im = Image.fromarray(p, "RGBA")
        yy, xx = np.mgrid[:h, :w]
        chk = np.zeros((h, w, 4), np.uint8)
        chk[...] = (70, 70, 78, 255)
        chk[((yy // 8 + xx // 8) % 2) == 0] = (48, 48, 54, 255)
        bg = Image.fromarray(chk, "RGBA")
        bg.alpha_composite(im)
        y = 6 + i * (h * k + 26)
        dr.text((10, y), lab, fill=(255, 220, 140))
        board.paste(bg.resize((w * k, h * k), Image.NEAREST).convert("RGB"), (10, y + 18))
    board.save(out / f"{name}.board.png")
    rec = {"name": name, "source_sha256": sha(raw), "candidate_png_sha256": sha((out / f"{name}.candidate.png").read_bytes()),
           "after_sha256": sha(new), "rects": [e["rect"] for e in spec["edits"]],
           "texts": [e.get("text", "") for e in spec["edits"]], "unchanged_outside_mask": outside_same,
           "graft": json.loads(rep.to_json())}
    (out / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rec = build(json.loads(Path(a.spec).read_text(encoding="utf-8")), Path(a.out))
    print(json.dumps({k: rec[k] for k in ("name", "source_sha256", "after_sha256", "unchanged_outside_mask")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
