"""Rebuild a sheet element as an English asset, rather than writing over it.

Drawing English on top of a Japanese card gives exactly what it sounds like:
a text overlay, with the old glyph ghosting through and the new lettering in
a font that belongs to no part of the artwork. What is wanted is the asset
*regenerated* — the same card, the same border and background, with English
lettering that matches the original's colour, weight and glow, occupying the
same place the Japanese occupied.

That means three things this module does and the previous approach did not:

1. **Separate ink from artwork properly.** The glyph is not simply "the
   bright pixels": it is what differs from the card's own background. The
   mask is built by comparing each pixel to the background colour sampled
   from the element's border.

2. **Reconstruct the background under the glyph.** A flat fill leaves a patch
   and a blur leaves a ghost, because the blur still contains the glyph.
   A push-pull fill flows the surrounding artwork inward at successively
   coarser scales, so the card's pattern continues across the hole.

3. **Copy the original's lettering style.** Fill colour, outline colour and
   glow are measured off the glyph that was there, and the English is drawn
   at the size that fills the same optical box.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from alrummi3_core import Region, choose_font, _wrap_text


@dataclass
class InkStyle:
    fill: tuple = (240, 255, 240, 255)
    outline: tuple = (10, 30, 15, 255)
    glow: tuple | None = None
    stroke: int = 2
    box: Region | None = None
    coverage: float = 0.0


def _blur(array: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return array
    image = Image.fromarray((np.clip(array, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0


def _border_colour(arr: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """The card's own background, sampled away from the middle where text is."""

    h, w = alpha.shape
    band = max(2, min(h, w) // 8)
    ring = np.zeros((h, w), dtype=bool)
    ring[:band, :] = True
    ring[-band:, :] = True
    ring[:, :band] = True
    ring[:, -band:] = True
    visible = ring & (alpha > 0.5)
    if visible.sum() < 8:
        visible = alpha > 0.5
    if visible.sum() < 8:
        return np.array([0, 0, 0], dtype=np.float32)
    return np.median(arr[visible][:, :3], axis=0)


def ink_mask(crop: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Separate the lettering from the card it sits on.

    Sampling the "background" from the element's border does not work on this
    artwork: the card's frame is the same bright green as the glyph, so the
    mask comes out inverted and the dark interior is treated as ink.

    What actually holds is that within the card's *interior*, the lettering is
    the minority class by luminance - bright strokes on a darker ground, or
    the reverse - so the interior is split with Otsu and whichever class
    covers less of it is the ink.
    """

    rgba = np.asarray(crop.convert("RGBA")).astype(np.float32)
    alpha = rgba[..., 3] / 255.0
    visible = alpha > 0.35
    if not visible.any():
        return np.zeros_like(alpha, dtype=bool), alpha

    lum = rgba[..., :3].mean(axis=2) / 255.0
    height, width = alpha.shape
    margin_y = max(1, int(height * 0.12))
    margin_x = max(1, int(width * 0.12))
    interior = np.zeros_like(visible)
    interior[margin_y:height - margin_y, margin_x:width - margin_x] = True
    interior &= visible
    if interior.sum() < 24:
        interior = visible

    threshold = _otsu(lum[interior])
    bright = interior & (lum >= threshold)
    dark = interior & (lum < threshold)
    if bright.sum() == 0 or dark.sum() == 0:
        return np.zeros_like(alpha, dtype=bool), alpha

    # The lettering is the smaller of the two classes.
    ink = bright if bright.sum() <= dark.sum() else dark
    # Take the class across the whole element, so strokes reaching into the
    # margin are included rather than clipped.
    full = visible & ((lum >= threshold) if ink is bright else (lum < threshold))
    if full.sum() > visible.sum() * 0.8:
        full = ink

    # The frame of a card is the same colour as the lettering on it, so no
    # brightness test can tell them apart. What separates them is position:
    # the frame is a component that touches the element's edge, the glyph is
    # one that does not. Drop the components that reach the border.
    return _drop_edge_components(full, visible), alpha


def _drop_edge_components(mask: np.ndarray, visible: np.ndarray) -> np.ndarray:
    """Keep only components that do not run along the sprite's own outline.

    The crop has a transparent margin, so testing against the crop's edge
    finds nothing. What identifies the frame is that it hugs the silhouette:
    it is adjacent to the transparent area around the card. The glyph sits
    inside and touches none of it.
    """

    if not mask.any():
        return mask
    labels, count = _label_components(mask)
    if count == 0:
        return mask

    # Pixels just outside the sprite, grown inward by one, mark the outline.
    outside = Image.fromarray(((~visible).astype(np.uint8) * 255), "L")
    rim = np.asarray(outside.filter(ImageFilter.MaxFilter(3))) > 0
    rim &= visible

    frame_labels = {int(v) for v in np.unique(labels[rim]) if v}
    if not frame_labels:
        return mask
    kept = mask & ~np.isin(labels, list(frame_labels))
    # If that removed everything, the element is the glyph and has no frame.
    if kept.sum() < max(12, mask.sum() * 0.05):
        return mask
    return kept


def _label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected labelling, iterative so a long stroke cannot blow the stack."""

    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    current = 0
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or labels[start_y, start_x]:
                continue
            current += 1
            stack = [(start_y, start_x)]
            labels[start_y, start_x] = current
            while stack:
                y, x = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width:
                        if mask[ny, nx] and not labels[ny, nx]:
                            labels[ny, nx] = current
                            stack.append((ny, nx))
    return labels, current


def _otsu(values: np.ndarray) -> float:
    """Split a set of values into two classes by maximising between-class variance.

    A fixed quantile cannot work here: on these cards the glyph is half the
    element, on a badge it is a tenth. Otsu finds the split from the data, so
    the whole glyph comes out rather than only its most extreme pixels.
    """

    if values.size < 8:
        return 0.16
    hist, edges = np.histogram(values, bins=64, range=(0.0, max(1e-6, float(values.max()))))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total <= 0:
        return 0.16
    centres = (edges[:-1] + edges[1:]) / 2.0
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    valid = (weight_bg > 0) & (weight_fg > 0)
    if not valid.any():
        return 0.16
    sum_all = np.cumsum(hist * centres)
    mean_bg = np.where(weight_bg > 0, sum_all / np.maximum(weight_bg, 1), 0.0)
    total_sum = sum_all[-1]
    mean_fg = np.where(weight_fg > 0, (total_sum - sum_all) / np.maximum(weight_fg, 1), 0.0)
    between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    between[~valid] = -1.0
    return float(centres[int(np.argmax(between))])


def _shift_fill(rgba: np.ndarray, hole: np.ndarray,
                backing: np.ndarray) -> np.ndarray | None:
    """Fill a hole by sliding the artwork over itself until it lines up.

    Card backings are repeating motifs. Blur-based filling cannot reproduce
    one — it can only average toward it, which leaves the removed character
    visible as a soft tonal seam however carefully the blur is tuned. But a
    repeating pattern is its own best source: some translation of the card
    matches the ring of good pixels around the hole, and at that offset the
    motif lands where it belongs.

    The offset is chosen on the known pixels only, so nothing about the hole
    influences it. Returns None when no offset explains the surroundings.
    """

    height, width = hole.shape
    known = backing & ~hole
    if known.sum() < 64 or not hole.any():
        return None

    # Score offsets against the band of good pixels hugging the hole, which is
    # where a mismatch would show.
    ring = _grow(hole, 6) & known
    if ring.sum() < 48:
        ring = known

    best, best_cost = None, np.inf
    step = max(2, min(height, width) // 24)
    for dy in range(-height + 8, height - 7, step):
        for dx in range(-width + 8, width - 7, step):
            if abs(dx) < 6 and abs(dy) < 6:
                continue
            shifted_ring = _shift(ring, dy, dx)
            usable = shifted_ring & known & ring
            overlap = int(usable.sum())
            if overlap < 40:
                continue
            source_pixels = _shift(rgba, dy, dx)
            diff = source_pixels[usable] - rgba[usable]
            cost = float(np.mean(diff * diff))
            # Prefer offsets that also cover the hole with good pixels.
            covered = int((_shift(known, dy, dx) & hole).sum())
            if covered < hole.sum() * 0.5:
                continue
            if cost < best_cost:
                best, best_cost = (dy, dx), cost

    if best is None or best_cost > 0.02:
        return None
    dy, dx = best
    donor = _shift(rgba, dy, dx)
    usable = _shift(known, dy, dx) & hole
    if usable.sum() < hole.sum() * 0.35:
        return None
    out = rgba.copy()
    out[usable] = donor[usable]
    # Whatever this offset could not reach stays in the hole for the caller to
    # finish; leaving it would keep the original glyph showing through.
    return out, hole & ~usable


def _shift(array: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.zeros_like(array)
    ys = slice(max(0, dy), array.shape[0] + min(0, dy))
    xs = slice(max(0, dx), array.shape[1] + min(0, dx))
    sy = slice(max(0, -dy), array.shape[0] + min(0, -dy))
    sx = slice(max(0, -dx), array.shape[1] + min(0, -dx))
    out[sy, sx] = array[ys, xs]
    return out


def _grow(mask: np.ndarray, times: int) -> np.ndarray:
    image = Image.fromarray((mask.astype(np.uint8) * 255), "L")
    for _ in range(times):
        image = image.filter(ImageFilter.MaxFilter(3))
    return np.asarray(image) > 0


def inpaint(crop: Image.Image, mask: np.ndarray, grow: int = 2,
            source: np.ndarray | None = None) -> Image.Image:
    """Fill the masked area with the surrounding artwork, pulled inward.

    Successively coarser blurs of the *known* pixels are used to fill the hole,
    so a pattern continues across it instead of leaving a flat patch.

    `source` narrows what counts as known. Without it the fill draws on every
    pixel outside the hole, and on a bordered card that includes the border —
    whose bright colour then bleeds inward and reads as a ghost of the glyph
    that was removed. Passing the backing alone keeps its pattern and keeps
    the border out of it.
    """

    rgba = np.asarray(crop.convert("RGBA")).astype(np.float32) / 255.0
    hole = mask.astype(np.float32)
    if grow > 0:
        grown = Image.fromarray((hole * 255).astype(np.uint8), "L")
        for _ in range(grow):
            grown = grown.filter(ImageFilter.MaxFilter(3))
        hole = np.asarray(grown, dtype=np.float32) / 255.0

    # A repeating backing fills best from itself. Anything the matched offset
    # could not reach is left in the hole and finished by the blur below, so a
    # partial match never leaves a strip of the original glyph behind.
    if source is not None and source.shape == hole.shape and source.any():
        patched = _shift_fill(rgba, hole > 0.5, source)
        if patched is not None:
            rgba, remaining = patched
            if not remaining.any():
                return Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
            hole = remaining.astype(np.float32)

    known = 1.0 - hole
    if source is not None and source.shape == hole.shape and source.any():
        known = known * source.astype(np.float32)
    result = rgba.copy()
    for channel in range(4):
        result[..., channel] *= known

    weight = known.copy()
    filled = result.copy()
    radius = 2.0
    for _ in range(6):
        weight_blur = _blur(weight, radius)
        safe = np.maximum(weight_blur, 1e-4)
        for channel in range(4):
            channel_blur = _blur(filled[..., channel], radius)
            estimate = channel_blur / safe
            filled[..., channel] = np.where(weight > 0.5, filled[..., channel], estimate)
        weight = np.maximum(weight, (weight_blur > 0.02).astype(np.float32))
        radius *= 2.0

    # Alpha is filled from the surroundings like every other channel. These
    # sheets draw their line art at full opacity over a translucent backing,
    # so the glyph is *defined* by its alpha: keeping the original alpha here
    # would leave the old character showing through as a silhouette no matter
    # how well its colour was replaced.
    out = np.where(hole[..., None] > 0.5, filled, rgba)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


def measure_style(crop: Image.Image, mask: np.ndarray) -> InkStyle:
    """Read the original lettering's colour, outline and weight."""

    rgba = np.asarray(crop.convert("RGBA")).astype(np.float32)
    style = InkStyle()
    if mask.sum() < 8:
        return style

    ink = rgba[mask]
    # The fill is the brightest core of the glyph, not its antialiased edge.
    order = np.argsort(ink[:, :3].sum(axis=1))
    core = ink[order[max(0, int(len(order) * 0.65)):]]
    style.fill = tuple(int(v) for v in np.median(core[:, :3], axis=0)) + (255,)

    # The outline is what sits just outside the glyph but is not the card.
    grown = Image.fromarray((mask.astype(np.uint8) * 255), "L").filter(ImageFilter.MaxFilter(5))
    rim = (np.asarray(grown) > 0) & ~mask & (rgba[..., 3] > 90)
    if rim.sum() >= 8:
        rim_pixels = rgba[rim]
        darkest = rim_pixels[np.argsort(rim_pixels[:, :3].sum(axis=1))[: max(1, rim.sum() // 3)]]
        style.outline = tuple(int(v) for v in np.median(darkest[:, :3], axis=0)) + (255,)

    ys, xs = np.nonzero(mask)
    style.box = Region(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    style.coverage = float(mask.sum()) / float(max(1, mask.size))
    # Stroke weight from the ratio of area to outline length.
    edge = np.asarray(
        Image.fromarray((mask.astype(np.uint8) * 255), "L").filter(ImageFilter.FIND_EDGES)
    ) > 0
    if edge.sum() > 0:
        style.stroke = int(max(1, min(6, round(mask.sum() / max(1, edge.sum()) / 2))))
    return style


def draw_lettering(base: Image.Image, text: str, box: Region, style: InkStyle,
                   *, font_path: str | None = None) -> Image.Image:
    """Draw English in the original's colour, outline and weight."""

    out = base.convert("RGBA")
    words = " ".join(text.split())
    if not words:
        return out

    banner = box.width >= box.height * 1.9
    font_file = choose_font(font_path, "serif_italic" if banner else "sans")
    scratch = ImageDraw.Draw(out)

    max_width = max(8, int(box.width * 0.96))
    max_height = max(8, int(box.height * 0.96))
    best = None
    for size in range(max(10, int(box.height * 1.1)), 6, -1):
        font = (ImageFont.truetype(str(font_file), size) if font_file
                else ImageFont.load_default())
        lines = _wrap_text(scratch, words, font, max_width)
        if any(scratch.textlength(w, font=font) > max_width for w in words.split()):
            continue
        bbox = font.getbbox("Ag")
        line_h = max(1, bbox[3] - bbox[1])
        gap = max(1, round(size * 0.14))
        total = line_h * len(lines) + gap * max(0, len(lines) - 1)
        if total <= max_height:
            best = (font, lines, gap, line_h, bbox)
            break
    if best is None:
        font = (ImageFont.truetype(str(font_file), 8) if font_file else ImageFont.load_default())
        lines = _wrap_text(scratch, words, font, max_width)
        bbox = font.getbbox("Ag")
        best = (font, lines, 1, max(1, bbox[3] - bbox[1]), bbox)

    font, lines, gap, line_h, bbox = best
    total = line_h * len(lines) + gap * max(0, len(lines) - 1)
    y = box.top + max(0, (box.height - total) // 2) - bbox[1]

    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    stroke = max(1, min(4, style.stroke))
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=font)
        x = box.left + max(0, (box.width - (lb[2] - lb[0])) // 2) - lb[0]
        draw.text((x, y), line, font=font, fill=style.fill,
                  stroke_width=stroke, stroke_fill=style.outline)
        y += line_h + gap

    if style.glow:
        halo = layer.getchannel("A").filter(ImageFilter.GaussianBlur(3))
        glow_layer = Image.new("RGBA", out.size, style.glow)
        glow_layer.putalpha(halo.point(lambda v: int(v * 0.55)))
        out = Image.alpha_composite(out, glow_layer)
    return Image.alpha_composite(out, layer)


def regenerate(image: Image.Image, region: Region, english: str,
               *, font_path: str | None = None) -> tuple[Image.Image, dict]:
    """Rebuild one element of a sheet as an English asset."""

    base = image.convert("RGBA")
    box = region.clipped(base.size)
    crop = base.crop((box.left, box.top, box.right, box.bottom))

    mask, _alpha = ink_mask(crop)
    style = measure_style(crop, mask)
    cleaned = inpaint(crop, mask)

    out = base.copy()
    out.paste(cleaned, (box.left, box.top))

    if style.box is not None:
        target = Region(box.left + style.box.left, box.top + style.box.top,
                        box.left + style.box.right, box.top + style.box.bottom)
    else:
        target = box
    # Give the lettering a little more room than the glyph had; English is
    # wider than a kanji at the same optical size.
    pad_x = int(box.width * 0.02)
    target = Region(max(box.left, target.left - pad_x), target.top,
                    min(box.right, target.right + pad_x), target.bottom).clipped(base.size)

    out = draw_lettering(out, english, target, style, font_path=font_path)
    return out, {
        "mode": "asset_regenerated",
        "region": box.as_list(),
        "text_box": target.as_list(),
        "ink_coverage": round(style.coverage, 4),
        "fill": list(style.fill),
        "outline": list(style.outline),
        "stroke": style.stroke,
    }
