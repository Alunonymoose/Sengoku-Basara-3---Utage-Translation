"""Targeted rebuilds for Utage roulette / fortune medallion texture sheets.

This is intentionally separate from the generic visual-copy renderer.  It
keeps the source sheet dimensions and atlas layout, detects the three large
fortune medallions, gives each one a stronger material finish, hides the old
lettering inside a rebuilt central plaque, and draws clean English labels with
the game's preferred bold italic serif look.

Deterministic only: numpy + Pillow, no network and no model required.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

import texture_fx
from alrummi3_core import Region, choose_font, _wrap_text


DEFAULT_LABELS = ["GREAT LUCK", "GOOD LUCK", "BAD LUCK"]


@dataclass(frozen=True)
class MedallionCandidate:
    box: Region
    area: int


def _components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    if cv2 is not None:
        count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
        return labels, count - 1

    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    current = 0
    stack: list[tuple[int, int]] = []
    for sy in range(height):
        for sx in range(width):
            if not mask[sy, sx] or labels[sy, sx]:
                continue
            current += 1
            labels[sy, sx] = current
            stack.append((sy, sx))
            while stack:
                y, x = stack.pop()
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < height and 0 <= nx < width \
                            and mask[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        stack.append((ny, nx))
    return labels, current


def _iou(a: Region, b: Region) -> float:
    ix = max(0, min(a.right, b.right) - max(a.left, b.left))
    iy = max(0, min(a.bottom, b.bottom) - max(a.top, b.top))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    union = a.width * a.height + b.width * b.height - inter
    return inter / max(1, union)


def find_medallions(image: Image.Image) -> list[Region]:
    """Find the three largest medallion-like isolated sprites on the sheet."""
    rgba = np.asarray(image.convert("RGBA"))
    alpha = rgba[..., 3]
    visible = alpha > 18
    labels, count = _components(visible)

    total = image.width * image.height
    found: list[MedallionCandidate] = []
    for index in range(1, count + 1):
        ys, xs = np.nonzero(labels == index)
        if len(ys) == 0:
            continue
        area = int(len(ys))
        if area < max(500, int(total * 0.007)):
            continue

        box = Region(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        if box.width < 40 or box.height < 40:
            continue
        aspect = box.width / max(1, box.height)
        fill = area / max(1, box.width * box.height)
        if not 0.48 <= aspect <= 1.55:
            continue
        if fill < 0.18:
            continue
        found.append(MedallionCandidate(box, area))

    found.sort(key=lambda item: (-item.area, item.box.left))
    chosen: list[MedallionCandidate] = []
    for candidate in found:
        if any(_iou(candidate.box, old.box) > 0.35 for old in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == 3:
            break

    chosen.sort(key=lambda item: item.box.left)
    return [item.box for item in chosen]


def _plaque_colour(image: Image.Image) -> tuple[int, int, int]:
    rgba = np.asarray(image.convert("RGBA"))
    alpha = rgba[..., 3] > 24
    h, w = alpha.shape
    y0, y1 = int(h * 0.18), int(h * 0.82)
    x0, x1 = int(w * 0.18), int(w * 0.82)
    middle = alpha[y0:y1, x0:x1]
    pixels = rgba[y0:y1, x0:x1, :3][middle]
    if len(pixels) < 8:
        pixels = rgba[..., :3][alpha]
    if len(pixels) < 8:
        return (116, 104, 68)
    value = np.median(pixels, axis=0)
    return tuple(int(v) for v in value)


def _make_clean_face(image: Image.Image, box: Region) -> Image.Image:
    out = image.convert("RGBA").copy()
    base = _plaque_colour(out)
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    radius = max(5, min(box.width, box.height) // 7)

    draw.rounded_rectangle(
        (box.left, box.top, box.right - 1, box.bottom - 1),
        radius=radius,
        fill=(base[0], base[1], base[2], 238),
        outline=(255, 247, 214, 105),
        width=max(1, radius // 4),
    )
    gloss_h = max(5, int(box.height * 0.30))
    draw.rounded_rectangle(
        (box.left + 3, box.top + 3, box.right - 4, min(box.bottom - 4, box.top + gloss_h)),
        radius=max(4, radius - 2),
        fill=(255, 255, 255, 28),
    )
    return Image.alpha_composite(out, overlay)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, box: Region):
    font_file = choose_font(None, "serif_italic")
    max_width = max(8, int(box.width * 0.92))
    max_height = max(8, int(box.height * 0.88))
    if font_file is None:
        font = ImageFont.load_default()
        return font, _wrap_text(draw, text, font, max_width), 1

    for size in range(max(9, int(box.height * 0.50)), 7, -1):
        font = ImageFont.truetype(str(font_file), size)
        lines = _wrap_text(draw, text, font, max_width)
        if any(draw.textlength(word, font=font) > max_width for word in text.split()):
            continue
        bbox = font.getbbox("Ag")
        line_h = max(1, bbox[3] - bbox[1])
        gap = max(1, round(size * 0.10))
        total = line_h * len(lines) + gap * max(0, len(lines) - 1)
        if total <= max_height:
            return font, lines, gap

    font = ImageFont.truetype(str(font_file), 8)
    return font, _wrap_text(draw, text, font, max_width), 1


def _letter(image: Image.Image, text: str, box: Region) -> Image.Image:
    out = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(out)
    text = " ".join(text.upper().split())
    font, lines, gap = _fit_font(draw, text, box)
    bbox = font.getbbox("Ag")
    line_h = max(1, bbox[3] - bbox[1])
    total = line_h * len(lines) + gap * max(0, len(lines) - 1)
    y = box.top + max(0, (box.height - total) // 2) - bbox[1]

    fill = (250, 246, 221, 255)
    stroke = (44, 30, 9, 255)
    shadow = (24, 15, 5, 190)
    size = getattr(font, "size", 10)
    shadow_stroke = max(1, round(size * 0.055))
    main_stroke = max(1, round(size * 0.025))

    for line in lines:
        lb = draw.textbbox((0, 0), line, font=font)
        width = lb[2] - lb[0]
        x = box.left + max(0, (box.width - width) // 2) - lb[0]
        draw.text((x + 2, y + 2), line, font=font, fill=shadow,
                  stroke_width=shadow_stroke, stroke_fill=shadow)
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=main_stroke, stroke_fill=stroke)
        y += line_h + gap
    return out


def rebuild_fortune_sheet(image: Image.Image, labels: list[str] | None = None) -> tuple[Image.Image, dict]:
    labels = list(labels or DEFAULT_LABELS)
    labels = [str(value).strip().upper() for value in labels if str(value).strip()]
    while len(labels) < 3:
        labels.append(DEFAULT_LABELS[len(labels)])
    labels = labels[:3]

    boxes = find_medallions(image)
    if len(boxes) != 3:
        raise ValueError(
            f"Expected three main medallions but confidently found {len(boxes)}. "
            "No texture was changed."
        )

    presets = ("Gold medallion", "Jade card", "Bronze relief")
    out = image.convert("RGBA").copy()
    items = []

    for box, label, preset in zip(boxes, labels, presets):
        crop = out.crop((box.left, box.top, box.right, box.bottom))
        styled, _ = texture_fx.style_image(crop, preset=preset, strength=0.80)

        face = Region(
            int(styled.width * 0.13),
            int(styled.height * 0.24),
            int(styled.width * 0.87),
            int(styled.height * 0.80),
        )
        styled = _make_clean_face(styled, face)
        styled = _letter(styled, label, face)

        out.paste(styled, (box.left, box.top), styled)
        items.append({"label": label, "preset": preset, "box": box.as_list()})

    return out, {
        "mode": "fortune_medallion_rebuild",
        "count": 3,
        "items": items,
        "source_dimensions": list(image.size),
        "candidate_dimensions": list(out.size),
        "dimensions_match": out.size == image.size,
    }
