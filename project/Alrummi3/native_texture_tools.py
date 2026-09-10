"""Native-art-preserving texture edits for Alrummi Next.

The old material presets repainted whole sprites.  That is the wrong default
for a localization tool: the game's artists already made the metal, jade,
glow and ornamentation.  These operations preserve that artwork and touch
only the lettering area selected by the operator.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from alrummi3_core import Region, choose_font, _wrap_text
from asset_gen import ink_mask, measure_style, inpaint


def _fit_serif(draw: ImageDraw.ImageDraw, text: str, box: Region):
    font_file = choose_font(None, "serif_italic")
    max_w = max(8, int(box.width * 0.94))
    max_h = max(8, int(box.height * 0.88))
    if font_file is None:
        font = ImageFont.load_default()
        return font, _wrap_text(draw, text, font, max_w), 1
    for size in range(max(9, int(box.height * 0.62)), 7, -1):
        font = ImageFont.truetype(str(font_file), size)
        lines = _wrap_text(draw, text, font, max_w)
        if any(draw.textlength(word, font=font) > max_w for word in text.split()):
            continue
        bbox = font.getbbox("Ag")
        line_h = max(1, bbox[3] - bbox[1])
        gap = max(1, int(size * 0.08))
        total = line_h * len(lines) + gap * max(0, len(lines) - 1)
        if total <= max_h:
            return font, lines, gap
    font = ImageFont.truetype(str(font_file), 8)
    return font, _wrap_text(draw, text, font, max_w), 1


def replace_lettering(
    image: Image.Image,
    region: Region,
    text: str,
    *,
    force_serif_italic: bool = False,
) -> tuple[Image.Image, dict]:
    """Remove the lettering in a tight box and rebuild only that box.

    This intentionally does not apply a colour gradient, sharpen pass or
    material preset to the surrounding sprite.
    """
    base = image.convert("RGBA")
    box = region.clipped(base.size)
    crop = base.crop((box.left, box.top, box.right, box.bottom))
    mask, _alpha = ink_mask(crop)
    if mask.sum() < 8:
        raise ValueError(
            "Could not isolate lettering in that box. Draw a tighter box around the text only."
        )
    style = measure_style(crop, mask)
    cleaned = inpaint(crop, mask, grow=2)
    out = base.copy()
    out.paste(cleaned, (box.left, box.top))

    words = " ".join(text.split())
    if not words:
        return out, {"mode": "erase_lettering", "region": box.as_list()}

    target = box
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if force_serif_italic:
        font, lines, gap = _fit_serif(draw, words, target)
    else:
        # Generic UI labels still default to the existing sans family; the
        # fortune/nameplate action explicitly requests the game's serif face.
        font_file = choose_font(None, "sans")
        max_w = max(8, int(target.width * 0.94))
        if font_file:
            chosen = None
            for size in range(max(9, int(target.height * 0.60)), 7, -1):
                f = ImageFont.truetype(str(font_file), size)
                lines0 = _wrap_text(draw, words, f, max_w)
                bb = f.getbbox("Ag")
                lh = max(1, bb[3] - bb[1])
                gp = max(1, int(size * 0.10))
                if lh * len(lines0) + gp * max(0, len(lines0) - 1) <= target.height * 0.88:
                    chosen = (f, lines0, gp)
                    break
            font, lines, gap = chosen or (ImageFont.truetype(str(font_file), 8), [words], 1)
        else:
            font = ImageFont.load_default()
            lines = _wrap_text(draw, words, font, max_w)
            gap = 1

    bbox = font.getbbox("Ag")
    line_h = max(1, bbox[3] - bbox[1])
    total = line_h * len(lines) + gap * max(0, len(lines) - 1)
    y = target.top + max(0, (target.height - total) // 2) - bbox[1]
    stroke = max(1, min(4, int(getattr(font, "size", 10) * 0.035)))
    outline = style.outline
    fill = style.fill
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=font)
        x = target.left + max(0, (target.width - (lb[2] - lb[0])) // 2) - lb[0]
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=outline)
        y += line_h + gap
    out = Image.alpha_composite(out, layer)
    return out, {
        "mode": "replace_lettering_native",
        "region": box.as_list(),
        "text": words,
        "font": str(getattr(font, "path", "system font")),
        "force_serif_italic": force_serif_italic,
        "ink_pixels_removed": int(mask.sum()),
        "fill": list(fill),
        "outline": list(outline),
    }


def _components(mask: np.ndarray):
    """Simple connected component boxes, large first."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    found = []
    for sy in range(height):
        for sx in range(width):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            xs, ys = [], []
            while stack:
                y, x = stack.pop()
                xs.append(x); ys.append(y)
                for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                    if 0 <= ny < height and 0 <= nx < width and mask[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx] = True
                        stack.append((ny,nx))
            found.append((len(xs), Region(min(xs), min(ys), max(xs)+1, max(ys)+1)))
    found.sort(key=lambda item: -item[0])
    return found


def find_fortune_cards(image: Image.Image) -> list[Region]:
    """Locate the three large left-to-right fortune cards on roulette sheets."""
    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    visible = alpha > 24
    total = image.width * image.height
    candidates = []
    for area, box in _components(visible):
        if area < total * 0.01 or box.width < 35 or box.height < 45:
            continue
        aspect = box.width / max(1, box.height)
        if 0.35 <= aspect <= 1.15:
            candidates.append((area, box))
    candidates.sort(key=lambda item: -item[0])
    boxes = [box for _area, box in candidates[:3]]
    boxes.sort(key=lambda b: b.left)
    return boxes


def relabel_fortune_cards(
    image: Image.Image,
    labels=("GREAT LUCK", "GOOD LUCK", "BAD LUCK"),
) -> tuple[Image.Image, dict]:
    """Relabel the three large fortune cards without restyling their artwork."""
    boxes = find_fortune_cards(image)
    if len(boxes) != 3:
        raise ValueError(
            f"Expected 3 large fortune cards, found {len(boxes)}. Nothing was changed."
        )
    out = image.convert("RGBA").copy()
    results = []
    for box, text in zip(boxes, labels):
        # Only the central face is eligible for cleanup.  Keeping well away
        # from the rim protects the artist-authored frame and highlights.
        text_box = Region(
            box.left + int(box.width * 0.10),
            box.top + int(box.height * 0.18),
            box.right - int(box.width * 0.10),
            box.bottom - int(box.height * 0.14),
        ).clipped(out.size)
        out, meta = replace_lettering(out, text_box, text, force_serif_italic=True)
        results.append({"card": box.as_list(), "text_box": text_box.as_list(), **meta})
    return out, {
        "mode": "fortune_relabel_native_art",
        "labels": list(labels),
        "cards": results,
        "dimensions": list(out.size),
    }
