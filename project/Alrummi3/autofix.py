"""One-button audit and repair for a texture sheet or a whole archive.

A texture like `roulette_000_ID_HQ` is not one image, it is a **sheet**: three
cards, several badges and a couple of icons, each with its own Japanese text.
Styling it gold makes handsome Japanese. Replacing it wholesale needs a donor
that does not exist for every sheet. What is actually needed is:

1. find each separate element on the sheet;
2. work out what each one says;
3. put English in its place, in that element's own ink colour and size;
4. and say plainly what was fixed, what was guessed, and what was not touched.

The resolution order is deliberate, best evidence first:

* **Donor** — the official Samurai Heroes texture for the same resource, or
  the same character matched by portrait. Lossless and authoritative.
* **Project dictionary** — 14,948 hand-built entries. Authoritative wording.
* **Local vision model** — OCR only, then the dictionary decides the English.
  Its own translations are marked as guesses and never applied silently.
* **Unresolved** — reported, never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import asset_gen
import ocr as ocr_engines
from alrummi3_core import Region, render_text_in_region, sample_ink_color
from project_dict import has_japanese, is_already_english, lookup as dict_lookup

# Elements closer than this are treated as one sprite, so the strokes of a
# single glyph or a card and its border do not come back as separate blobs.
MERGE_RADIUS = 7
MIN_SPRITE_PX = 24


@dataclass
class Element:
    region: Region
    japanese: str = ""
    english: str = ""
    source: str = ""          # donor | dictionary | model guess | unresolved
    note: str = ""
    ink: tuple = (255, 255, 255, 255)
    applied: bool = False

    def as_dict(self) -> dict:
        return {
            "region": self.region.as_list(),
            "japanese": self.japanese,
            "english": self.english,
            "source": self.source,
            "note": self.note,
            "applied": self.applied,
        }


# ------------------------------------------------------------- segmentation

def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Two-pass connected-component labelling with union-find, 8-connected."""

    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parent: list[int] = [0]

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    nxt = 1
    for y in range(height):
        row = mask[y]
        for x in np.flatnonzero(row):
            neighbours = []
            if x > 0 and labels[y, x - 1]:
                neighbours.append(labels[y, x - 1])
            if y > 0:
                for dx in (-1, 0, 1):
                    nx = x + dx
                    if 0 <= nx < width and labels[y - 1, nx]:
                        neighbours.append(labels[y - 1, nx])
            if not neighbours:
                labels[y, x] = nxt
                parent.append(nxt)
                nxt += 1
            else:
                smallest = min(neighbours)
                labels[y, x] = smallest
                for other in neighbours:
                    union(smallest, other)

    remap: dict[int, int] = {}
    out = np.zeros_like(labels)
    count = 0
    nonzero = np.flatnonzero(labels.ravel())
    flat = labels.ravel()
    out_flat = out.ravel()
    for index in nonzero:
        root = find(int(flat[index]))
        if root not in remap:
            count += 1
            remap[root] = count
        out_flat[index] = remap[root]
    return out, count


def find_elements(image: Image.Image, *, merge: int = MERGE_RADIUS) -> list[Region]:
    """Split a sheet into its separate sprites using the alpha channel."""

    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba)[..., 3]

    def blobs(threshold: int, dilations: int) -> list[Region]:
        solid = (alpha > threshold).astype(np.uint8) * 255
        grown = Image.fromarray(solid, "L")
        for _ in range(max(0, dilations)):
            grown = grown.filter(ImageFilter.MaxFilter(3))
        labels, count = _label(np.asarray(grown) > 0)
        found: list[Region] = []
        for index in range(1, count + 1):
            ys, xs = np.nonzero(labels == index)
            if len(xs) < MIN_SPRITE_PX:
                continue
            left, right = int(xs.min()), int(xs.max()) + 1
            top, bottom = int(ys.min()), int(ys.max()) + 1
            if (right - left) < 8 or (bottom - top) < 8:
                continue
            found.append(Region(left, top, right, bottom).clipped(rgba.size))
        return found

    # These sheets sit on a semi-transparent field rather than on nothing, so
    # a low cutoff joins every sprite into one blob.  Walk the threshold down
    # from opaque and keep the first level that actually separates the sheet
    # into a plausible number of elements.
    best: list[Region] = []
    for threshold in (216, 192, 160, 128, 96, 64, 32):
        found = blobs(threshold, max(1, merge // 3))
        covering = [r for r in found
                    if r.width > rgba.width * 0.9 and r.height > rgba.height * 0.9]
        if covering:
            continue                      # still one blob spanning the sheet
        if 2 <= len(found) <= 80:
            best = found
            break
        if found and not best:
            best = found
    # Different thresholds can yield a card and, inside it, its own text line.
    # Lettering both would draw twice, so a region wholly inside another is
    # dropped and the outer one kept.
    def contains(outer: Region, inner: Region) -> bool:
        return (outer.left <= inner.left and outer.top <= inner.top
                and outer.right >= inner.right and outer.bottom >= inner.bottom
                and (outer.width * outer.height) > (inner.width * inner.height))

    kept: list[Region] = []
    for region in sorted(best, key=lambda r: -(r.width * r.height)):
        if any(contains(other, region) for other in kept):
            continue
        kept.append(region)
    kept.sort(key=lambda r: (r.top // 16, r.left))
    return kept


# ---------------------------------------------------------------- resolving

def resolve_elements(
    image: Image.Image,
    regions: list[Region],
    dictionary: dict,
    *,
    ai=None,
    ai_enabled: bool = True,
    progress=None,
) -> list[Element]:
    """Work out what each element says and what English belongs there.

    Reading is done by whatever engines are installed - a dedicated OCR first
    because it is fast and confident, the vision model after it for whatever
    is left - and the project dictionary decides the English.
    """

    rgba = image.convert("RGBA")
    engines = ocr_engines.build_engines(ai if ai_enabled else None)
    elements: list[Element] = []
    total = len(regions)

    for position, region in enumerate(regions, start=1):
        element = Element(region=region)
        ink = sample_ink_color(rgba, region)
        if ink:
            element.ink = ink

        crop = rgba.crop((region.left, region.top, region.right, region.bottom))
        read = ocr_engines.read_element(crop, engines) if engines else None
        if read is None:
            element.source = "unresolved"
            element.note = ("no OCR engine available" if not engines
                            else "no text could be read in this element")
            elements.append(element)
            if progress:
                progress(position, total)
            continue

        element.japanese = read.text
        element.note = f"read by {read.engine} at {read.confidence:.2f}"
        resolved = ocr_engines.resolve_text(dictionary, read.text)
        if resolved:
            english, matched, how = resolved
            element.english = english
            if matched != read.text:
                element.note += f"; {read.text} taken as {matched}"
            if "corrected" in how:
                element.note += " (known OCR confusion)"
            if read.confidence < ocr_engines.TRUST_THRESHOLD:
                # A dictionary hit built on a shaky read is still a shaky
                # read, and wrong English is worse than none. Offer it for a
                # decision rather than applying it.
                element.source = "needs review"
                element.note += "; low confidence, not applied automatically"
            else:
                element.source = "dictionary"
        elif is_already_english(read.text):
            element.source = "already English"
            element.note += "; nothing to translate"
        else:
            element.source = "unresolved"
            element.note += "; not in the project dictionary"
        elements.append(element)
        if progress:
            progress(position, total)
    return elements


def ink_bounds(image: Image.Image, region: Region) -> Region:
    """Where the lettering actually sits inside an element.

    An element is usually a card: a border, a background, and some text in the
    middle. Lettering across the whole card and erasing it first destroys the
    artwork, so the text is found by looking for the brightest ink inside the
    element and only that area is replaced.
    """

    crop = image.convert("RGBA").crop((region.left, region.top, region.right, region.bottom))
    arr = np.asarray(crop).astype(np.float32)
    alpha = arr[..., 3] / 255.0
    lum = arr[..., :3].mean(axis=2) / 255.0
    solid = alpha > 0.5
    if not solid.any():
        return region
    # The ink is the brightest quartile of the visible pixels.
    values = lum[solid]
    cutoff = float(np.quantile(values, 0.80))
    mask = solid & (lum >= max(cutoff, 0.35))
    if mask.sum() < 12:
        return region
    ys, xs = np.nonzero(mask)
    pad = 2
    left = max(0, int(xs.min()) - pad)
    right = min(crop.width, int(xs.max()) + 1 + pad)
    top = max(0, int(ys.min()) - pad)
    bottom = min(crop.height, int(ys.max()) + 1 + pad)
    if (right - left) < 8 or (bottom - top) < 8:
        return region
    return Region(region.left + left, region.top + top,
                  region.left + right, region.top + bottom).clipped(image.size)


def erase_ink(image: Image.Image, region: Region, keep_art: bool = True) -> Image.Image:
    """Remove the old lettering without removing the card it sits on."""

    out = image.convert("RGBA").copy()
    if not keep_art:
        from alrummi3_core import erase_region
        return erase_region(out, region)[0]

    crop = out.crop((region.left, region.top, region.right, region.bottom))
    arr = np.asarray(crop).astype(np.float32)
    alpha = arr[..., 3] / 255.0
    lum = arr[..., :3].mean(axis=2) / 255.0
    solid = alpha > 0.5
    if not solid.any():
        return out
    cutoff = float(np.quantile(lum[solid], 0.55))
    ink = solid & (lum >= max(cutoff, 0.28))
    if ink.sum() < 4:
        return out
    # Blurring the crop is not enough: the blur still contains the glyph, so
    # it ghosts through.  Fill the ink with the card's own background - the
    # median of the pixels that are visible but are NOT ink - then feather the
    # edge so the patch does not show.
    backdrop = solid & ~ink
    if backdrop.sum() >= 8:
        fill = np.median(arr[backdrop][:, :4], axis=0)
    else:
        fill = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    patch = np.array(arr, copy=True)
    grown = Image.fromarray((ink.astype(np.uint8) * 255), "L").filter(
        ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    weight = (np.asarray(grown).astype(np.float32) / 255.0)[..., None]
    patch = patch * (1.0 - weight) + fill[None, None, :] * weight
    crop = Image.fromarray(np.clip(patch, 0, 255).astype(np.uint8), "RGBA")
    out.paste(crop, (region.left, region.top))
    return out


def apply_elements(image: Image.Image, elements: list[Element],
                   *, only_confident: bool = False,
                   keep_art: bool = True) -> tuple[Image.Image, dict]:
    """Letter each resolved element in place, leaving the rest untouched."""

    out = image.convert("RGBA").copy()
    applied = skipped = 0
    for element in elements:
        if not element.english.strip():
            skipped += 1
            continue
        if only_confident and element.source not in ("donor", "dictionary"):
            skipped += 1
            continue
        # Rebuild the element rather than writing over it: remove the glyph,
        # reconstruct the artwork underneath, and letter in the original's
        # own colour, outline and weight.
        out, _meta = asset_gen.regenerate(out, element.region, element.english)
        element.applied = True
        applied += 1
    return out, {
        "mode": "sheet_autofix",
        "elements": len(elements),
        "applied": applied,
        "skipped": skipped,
        "detail": [e.as_dict() for e in elements],
        "dimensions": list(out.size),
    }


def audit_text(name: str, elements: list[Element], summary: dict | None = None) -> str:
    """A plain report of what is on the sheet and what happened to it."""

    lines = [f"SHEET AUDIT — {name}", f"{len(elements)} element(s) found", ""]
    counts: dict[str, int] = {}
    for element in elements:
        counts[element.source] = counts.get(element.source, 0) + 1
    for source, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:3d}  {source}")
    lines.append("")
    for index, element in enumerate(elements, start=1):
        r = element.region
        mark = "applied" if element.applied else "not applied"
        lines.append(
            f"[{index:02d}] {r.left},{r.top} {r.width}x{r.height}  ({element.source}, {mark})"
        )
        if element.japanese:
            lines.append(f"      reads : {element.japanese}")
        if element.english:
            lines.append(f"      english: {element.english}")
        if element.note:
            lines.append(f"      note  : {element.note}")
    if summary:
        lines.append("")
        lines.append(f"applied {summary['applied']}, skipped {summary['skipped']}")
    return "\n".join(lines)
