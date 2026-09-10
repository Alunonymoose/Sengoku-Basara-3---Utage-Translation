"""Recognising each asset on a texture sheet, and rebuilding it in English.

The previous approach guessed at sprite boundaries from pixels: threshold the
sheet, take connected components, hope each blob is one asset. It produced
text overlays, because it never reliably found *the lettering* — on an omikuji
card the glyph and the card's own border are the same shade of green, so every
colour rule that separated them on one card inverted on the next.

Two sources of truth replace the guessing:

**The layout says what exists.** Every `id\\lsp\\...` resource names its sprite
nodes and the texture each draws from (see `layout.py`). A sheet is no longer
an anonymous image — it is `waku1`, `sitaji1`, `hanko`, `point`, by name, with
`moji` marking lettering. That gives the inventory and the vocabulary.

**A text detector says where the lettering is.** RapidOCR's detection stage is
a trained model; it puts a tight box on each glyph group and is not fooled by
a border that happens to share the glyph's colour. Asking it where the text is
turns an unsolved segmentation problem into a solved one — and the box it
returns is the box the English must occupy.

What remained was one real bug. Sampling the background from the box's rim
picked up the transparent magenta *outside* a card whenever the box reached
the card's edge, which flipped the mask and selected the entire card as ink.
Sampling only opaque pixels fixes it: a transparent pixel is not part of the
sprite, so it cannot be part of the sprite's background.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter

from alrummi3_core import Region

OPAQUE = 110          # a pixel below this alpha is not part of the sprite
_MIN_INK = 0.02       # a mask this sparse found nothing
_MAX_INK = 0.72       # a mask this dense selected the artwork, not the ink


@dataclass
class Asset:
    """One recognised thing on a sheet."""

    box: Region
    japanese: str = ""
    confidence: float = 0.0
    english: str = ""
    node: str = ""
    role: str = ""
    mask: np.ndarray | None = field(default=None, repr=False)
    note: str = ""
    done: bool = False           # already English; needs nothing

    @property
    def ready(self) -> bool:
        if self.done:
            return False
        return bool(self.english) and self.mask is not None and self.mask.any()

    def describe(self) -> str:
        where = f"({self.box.left},{self.box.top}) {self.box.width}x{self.box.height}"
        bits = [where]
        if self.node:
            bits.append(self.node + (f" [{self.role}]" if self.role else ""))
        if self.japanese:
            bits.append(f"{self.japanese!r} @{self.confidence:.2f}")
        if self.english:
            bits.append(f"-> {self.english!r}")
        if self.note:
            bits.append(self.note)
        return "  ".join(bits)


def _boxes(image: Image.Image, engine, scales=(2, 3)) -> list:
    """Detected text boxes, merged across scales, best confidence winning."""

    found: list = []
    for scale in scales:
        try:
            found.extend(engine.read_regions(image, scale=scale))
        except Exception:
            continue
    found.sort(key=lambda r: -r.confidence)

    kept: list = []
    for read in found:
        if not read.box:
            continue
        if any(_overlap(read.box, other.box) > 0.45 for other in kept):
            continue
        kept.append(read)
    kept.sort(key=lambda r: (r.box[1], r.box[0]))
    return kept


def _overlap(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if not inter:
        return 0.0
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / max(1, union)


def _trim_to_sprite(alpha: np.ndarray, box) -> Region | None:
    """Shrink a box until every edge row and column carries opaque pixels.

    A detector box often spills a few pixels past the card it sits on. Those
    pixels belong to whatever is behind the sprite, and letting them into the
    background sample is what inverted the mask.
    """

    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(alpha.shape[1], x1), min(alpha.shape[0], y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    # Anything not fully transparent belongs to the sprite: a card's backing is
    # translucent, and trimming on opacity would cut into the artwork.
    solid = alpha[y0:y1, x0:x1] > 8
    if not solid.any():
        return None

    rows = solid.mean(axis=1)
    cols = solid.mean(axis=0)
    top = int(np.argmax(rows > 0.10))
    bottom = len(rows) - int(np.argmax(rows[::-1] > 0.10))
    left = int(np.argmax(cols > 0.10))
    right = len(cols) - int(np.argmax(cols[::-1] > 0.10))
    if bottom - top < 4 or right - left < 4:
        return None
    return Region(x0 + left, y0 + top, x0 + right, y0 + bottom)


try:                                     # already present: RapidOCR needs it
    import cv2
except Exception:                        # pragma: no cover - fallback path
    cv2 = None


def _components(mask: np.ndarray):
    """Label 4-connected runs.

    OpenCV does this in C. The Python flood below is correct but walks every
    pixel through an interpreter loop, which on a 512-pixel sheet costs enough
    to be felt, so it is only the fallback.
    """

    if cv2 is not None:
        count, labels = cv2.connectedComponents(
            mask.astype(np.uint8), connectivity=4)
        return labels, count - 1         # label 0 is the background

    height, width = mask.shape
    labels = np.zeros((height, width), np.int32)
    current = 0
    stack: list[tuple[int, int]] = []
    for sy in range(height):
        for sx in range(width):
            if not mask[sy, sx] or labels[sy, sx]:
                continue
            current += 1
            stack.append((sy, sx))
            labels[sy, sx] = current
            while stack:
                y, x = stack.pop()
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < height and 0 <= nx < width \
                            and mask[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        stack.append((ny, nx))
    return labels, current


def _drop_frames(mask: np.ndarray) -> np.ndarray:
    """Remove components shaped like the card's border rather than a glyph.

    A border wraps the crop: its bounding box spans nearly the whole area
    while the component itself fills very little of that box. A glyph, even a
    sprawling one, does not touch all four edges at once.
    """

    # A glyph often brushes the frame, and at the antialiased edge the two
    # merge into one component that no shape test can classify. Eroding first
    # snaps that one-pixel bridge; survivors are grown back afterwards.
    core = _erode(mask)
    if not core.any():
        core = mask

    labels, count = _components(core)
    if count == 0:
        return mask
    height, width = mask.shape
    # Frames sit a few pixels inside the crop rather than flush against it, so
    # "at the edge" has to be measured proportionally.
    margin_x = max(2, int(width * 0.07))
    margin_y = max(2, int(height * 0.07))
    dropped = np.zeros_like(core)
    for index in range(1, count + 1):
        ys, xs = np.nonzero(labels == index)
        if len(ys) == 0:
            continue
        box_w = xs.max() - xs.min() + 1
        box_h = ys.max() - ys.min() + 1
        spans_x = box_w / width
        spans_y = box_h / height
        fill = len(ys) / max(1.0, box_w * box_h)
        # int() matters: adding numpy bools is logical OR, so a plain sum of
        # these tests would only ever be True or False, never a count.
        touches = (int(xs.min() <= margin_x) + int(xs.max() >= width - 1 - margin_x)
                   + int(ys.min() <= margin_y) + int(ys.max() >= height - 1 - margin_y))

        # A border: wraps most of the crop while enclosing mostly empty space.
        border = spans_x > 0.85 and spans_y > 0.85 and fill < 0.40 and touches >= 3
        # A border the crop cut through: a long thin run down one whole side.
        thin = (spans_x < 0.14 and spans_y > 0.75) or (spans_y < 0.14 and spans_x > 0.75)
        if border or (thin and touches >= 2):
            dropped[labels == index] = True

    if not dropped.any():
        return mask
    # Grow the rejected cores back over their antialiased skirt, but only into
    # pixels the kept ink does not claim, so a touching glyph keeps its edge.
    keep_core = core & ~dropped
    frame = _dilate(_dilate(dropped)) & mask & ~_dilate(keep_core)
    out = mask & ~frame
    if out.sum() < max(12, mask.sum() * 0.05):
        return mask
    return out


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """The mask with its enclosed interior filled in.

    Everything reachable from outside the shape is the outside; what is left
    is the shape and whatever it encloses. Padding by a pixel guarantees the
    flood has somewhere to start even when the shape meets the crop's edge.
    """

    padded = np.pad(mask, 1, constant_values=False)
    if cv2 is not None:
        free = (~padded).astype(np.uint8)
        # floodFill's scratch buffer must be two pixels larger than the image.
        scratch = np.zeros((free.shape[0] + 2, free.shape[1] + 2), np.uint8)
        cv2.floodFill(free, scratch, (0, 0), 2)
        outside = free == 2
    else:                                # pragma: no cover - fallback path
        outside = np.zeros_like(padded)
        outside[0, 0] = True
        while True:
            grown = _dilate(outside) & ~padded
            if grown.sum() == outside.sum():
                break
            outside = grown
    return ~outside[1:-1, 1:-1]


def _drop_outline(mask: np.ndarray, _silhouette=None) -> np.ndarray:
    """Remove a border that is fused to the lettering it surrounds.

    Where a card's glyph is drawn out to the edges it touches the frame, and
    the two become one connected run that no component test can classify —
    eroding first snaps a one-pixel bridge but not a real join.

    What still tells them apart is that a frame *encloses*. Filling a
    component's interior turns the frame into a solid card shape, and the
    frame is then just that shape's outer band, while the lettering sits
    inside it. The band is only removed when it is mostly inked, which is
    what an enclosing border looks like; lettering that merely brushes the
    edge inks little of it and is left alone.
    """

    labels, count = _components(mask)
    out = mask.copy()
    for index in range(1, count + 1):
        part = labels == index
        if part.sum() < 64:
            continue
        filled = _fill_holes(part)
        interior = filled & ~part
        if interior.sum() < part.sum() * 0.5:
            continue                      # encloses nothing worth speaking of
        band = filled & ~_erode_n(filled, _outline_width(filled))
        if not band.any():
            continue
        inked = part & band
        if inked.sum() < band.sum() * 0.55:
            continue                      # not a border tracing that shape
        remainder = part & ~inked
        if remainder.sum() < part.sum() * 0.08:
            continue                      # the whole component was the border
        out[inked] = False
    return out


def _outline_width(silhouette: np.ndarray) -> int:
    ys, xs = np.nonzero(silhouette)
    if len(ys) == 0:
        return 2
    extent = min(int(xs.max() - xs.min()) + 1, int(ys.max() - ys.min()) + 1)
    return max(2, min(8, int(extent * 0.055)))


def _erode_n(mask: np.ndarray, times: int) -> np.ndarray:
    out = mask
    for _ in range(max(0, times)):
        out = _erode(out)
    return out


def _erode(mask: np.ndarray) -> np.ndarray:
    image = Image.fromarray((mask.astype(np.uint8) * 255), "L")
    return np.asarray(image.filter(ImageFilter.MinFilter(3))) > 0


def _dilate(mask: np.ndarray) -> np.ndarray:
    image = Image.fromarray((mask.astype(np.uint8) * 255), "L")
    return np.asarray(image.filter(ImageFilter.MaxFilter(3))) > 0


def _alpha_ink(alpha: np.ndarray) -> np.ndarray | None:
    """The line art, taken straight from the alpha channel.

    These sheets are built in layers: the glyph strokes and the card's frame
    are drawn at full opacity, while the card's own backing pattern is
    translucent. So the artwork separates itself — no colour rule needed, and
    none of the green-glyph-on-green-border trouble. The frame comes along
    with the glyph, but as its own connected component, which `_drop_frames`
    then removes.

    Returns None when the crop has no such structure (a fully opaque sheet),
    leaving the colour-based route to handle it.
    """

    inside = alpha[alpha > 8]
    if inside.size < 16:
        return None
    high = float(np.percentile(inside, 96))
    low = float(np.percentile(inside, 40))
    if high < 160 or high - low < 60:
        return None                       # no opacity layering to exploit
    return alpha >= (low + high) / 2.0


def ink_in_box(image: Image.Image, box: Region) -> np.ndarray | None:
    """The lettering inside a detector box, as a boolean mask over that box."""

    rgba = np.asarray(image.convert("RGBA")).astype(np.float32)
    crop = rgba[box.top:box.bottom, box.left:box.right]
    if crop.size == 0:
        return None
    alpha = crop[:, :, 3]

    layered = _alpha_ink(alpha)
    if layered is not None:
        mask = _drop_outline(_drop_frames(layered))
        coverage = mask.sum() / max(1, mask.size)
        if _MIN_INK <= coverage <= _MAX_INK:
            return mask

    solid = alpha >= OPAQUE
    if solid.sum() < 16:
        return None

    rim = np.zeros(crop.shape[:2], bool)
    band = max(1, min(3, min(crop.shape[:2]) // 8))
    rim[:band] = rim[-band:] = True
    rim[:, :band] = rim[:, -band:] = True
    sample = crop[rim & solid]
    if len(sample) < 8:
        sample = crop[solid]
    background = np.median(sample[:, :3], axis=0)

    distance = np.linalg.norm(crop[:, :, :3] - background, axis=2)
    distance[~solid] = 0.0
    spread = float(np.percentile(distance[solid], 99))
    if spread < 12.0:
        return None                      # nothing here differs from the card

    mask = (distance > spread * 0.5) & solid
    mask = _drop_frames(mask)
    coverage = mask.sum() / max(1, solid.sum())
    if coverage < _MIN_INK or coverage > _MAX_INK:
        return None
    return mask


def ink_halo(image: Image.Image, box: Region, mask: np.ndarray,
             reach: int = 3) -> np.ndarray:
    """The mask widened to swallow the glyph's antialiased skirt.

    A stroke does not stop dead at the alpha cut: around it is a fringe of
    part-opaque pixels carrying the ink's colour. Those pixels are not in the
    mask, so the fill treats them as good surroundings and pulls them into the
    hole — which is what leaves a pale ghost of the old character across the
    card's backing. Anything near the mask that is brighter than the backing
    belongs to the stroke, so it is put into the hole too.
    """

    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    crop = alpha[box.top:box.bottom, box.left:box.right].astype(np.float32)
    if crop.shape != mask.shape or not mask.any():
        return mask
    # Measure the backing from the backing, not merely from "outside the mask":
    # the border is outside the mask too, and its full opacity would drag the
    # level up to 255 and make the test match nothing at all.
    surface = backing_of(image, box)
    if surface is None:
        surface = ~mask
    backing = crop[surface]
    if backing.size < 8:
        return mask
    level = float(np.median(backing))
    spread = float(np.percentile(backing, 88)) - level
    near = mask
    for _ in range(max(1, reach)):
        near = _dilate(near)
    return mask | (near & (crop > level + max(6.0, spread * 1.5)))


def backing_of(image: Image.Image, box: Region) -> np.ndarray | None:
    """The card's own surface: everything that is not line art.

    Both the glyph and the border are drawn at full opacity, so excluding the
    whole opaque layer leaves the translucent backing — the only part of the
    crop that should feed a repair.
    """

    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    crop = alpha[box.top:box.bottom, box.left:box.right]
    if crop.size == 0:
        return None
    layered = _alpha_ink(crop.astype(np.float32))
    if layered is None:
        return None
    backing = ~layered
    return backing if backing.sum() >= 32 else None


def find_assets(image: Image.Image, engine, *, layout=None,
                texture_name: str = "") -> list[Asset]:
    """Every recognisable asset on a sheet, located and described."""

    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    named = []
    if layout is not None and texture_name:
        named = [n for n in layout.nodes_using(texture_name)]

    assets: list[Asset] = []
    for read in _boxes(image, engine):
        region = _trim_to_sprite(alpha, read.box)
        if region is None:
            continue
        asset = Asset(box=region, japanese=read.text or "",
                      confidence=float(read.confidence or 0.0))
        asset.mask = ink_in_box(image, region)
        if asset.mask is None:
            asset.note = "could not separate lettering from artwork"
        assets.append(asset)

    # Layout names are listed in draw order; attach them to assets top-to-bottom
    # so the report can say which node an asset most likely belongs to.
    lettering = [n for n in named if n.role in ("lettering", "stamp")]
    for asset, node in zip(assets, lettering):
        asset.node, asset.role = node.name, node.role
    return assets


def translate_assets(assets: list[Asset], dictionary: dict, *,
                     reletter: bool = False) -> list[Asset]:
    """Fill in the English for each asset from the project dictionary.

    `reletter` is for a sheet that is already English but badly done — an
    early machine-translated patch with the wording pasted over the artwork.
    There is nothing to translate there, so the default reports it as
    finished; with this set, each asset is rebuilt from the wording already on
    it, which erases the old lettering properly and redraws it in the artwork's
    own colour and weight.
    """

    from ocr import resolve_text
    from project_dict import has_japanese

    for asset in assets:
        if not asset.japanese:
            asset.note = asset.note or "no text read"
            continue
        # A sheet that has already been done reads back as English. Looking
        # that up in a Japanese-to-English dictionary can only miss, and
        # reporting the miss as "no dictionary entry" makes finished work look
        # like outstanding work.
        if not has_japanese(asset.japanese):
            if reletter:
                # Nothing to translate — redraw the wording that is already
                # there, which is the point when the existing lettering was
                # pasted on rather than built into the artwork.
                asset.english = asset.japanese
                asset.note = "re-lettered from the wording already on the sheet"
                continue
            asset.done = True
            asset.note = "already English — nothing to do"
            continue
        hit = resolve_text(dictionary, asset.japanese)
        if not hit:
            asset.note = asset.note or "no dictionary entry"
            continue
        english, matched, how = hit
        asset.english = english or ""
        if matched != asset.japanese:
            asset.note = how
            asset.japanese = matched
    return assets


def rebuild_sheet(image: Image.Image, assets: list[Asset], *,
                  font_path: str | None = None) -> tuple[Image.Image, list[str]]:
    """Regenerate every ready asset in place, leaving the artwork alone."""

    from asset_gen import inpaint, measure_style, draw_filled

    out = image.convert("RGBA")
    report: list[str] = []
    for asset in assets:
        if not asset.ready:
            report.append(f"skipped  {asset.describe()}")
            continue
        box = asset.box
        crop = out.crop((box.left, box.top, box.right, box.bottom))
        style = measure_style(crop, asset.mask)
        # Measure the style off the stroke itself, but erase its fringe too.
        hole = ink_halo(out, box, asset.mask)
        cleaned = inpaint(crop, hole, source=backing_of(out, box))
        out.paste(cleaned, (box.left, box.top))

        # The English goes where the ink was, not where the detector's box was.
        inner = style.box or Region(0, 0, box.width, box.height)
        target = Region(box.left + inner.left, box.top + inner.top,
                        box.left + inner.right, box.top + inner.bottom)
        out = draw_filled(out, asset.english, target, style, font_path=font_path)
        report.append(f"rebuilt  {asset.describe()}")
    return out, report
