"""V4.1 high-quality texture editing.

Unlike the V4 whole-sheet path, V4.1 uses the image model as a lettering
in-painter.  The model receives the complete native sheet for context, but
only pixels inside detected/known lettering regions are copied back.  Every
pixel outside those regions remains byte-for-byte identical in RGBA preview
space.

Important: alpha is deliberately allowed to change *inside* a lettering box.
English glyphs have a different silhouette from Japanese glyphs, so restoring
the old alpha there would literally mask new letters into the old kanji shape.
Outside the edit boxes, alpha and hidden RGB remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from alrummi3_core import Region
import v4_image_edit as base


@dataclass(frozen=True)
class TextEdit:
    box: Region
    japanese: str = ""
    english: str = ""


def _expand(box: Region, size: tuple[int, int]) -> Region:
    width, height = size
    pad_x = max(5, round(box.width * 0.40))
    pad_y = max(4, round(box.height * 0.45))
    return Region(
        max(0, box.left - pad_x),
        max(0, box.top - pad_y),
        min(width, box.right + pad_x),
        min(height, box.bottom + pad_y),
    )


def _overlap_or_touch(a: Region, b: Region, gap: int = 3) -> bool:
    return not (
        a.right + gap < b.left or b.right + gap < a.left
        or a.bottom + gap < b.top or b.bottom + gap < a.top
    )


def _union(a: Region, b: Region) -> Region:
    return Region(min(a.left, b.left), min(a.top, b.top), max(a.right, b.right), max(a.bottom, b.bottom))


def merged_edit_boxes(edits: list[TextEdit], size: tuple[int, int]) -> list[Region]:
    boxes = [_expand(edit.box.clipped(size), size) for edit in edits]
    merged: list[Region] = []
    for box in boxes:
        for index, old in enumerate(merged):
            if _overlap_or_touch(old, box):
                merged[index] = _union(old, box).clipped(size)
                break
        else:
            merged.append(box)
    # A merge can make two previously separate boxes touch, so collapse until
    # stable. Texture sheets have few text boxes; O(n^2) is trivial here.
    changed = True
    while changed:
        changed = False
        out: list[Region] = []
        for box in merged:
            for index, old in enumerate(out):
                if _overlap_or_touch(old, box):
                    out[index] = _union(old, box).clipped(size)
                    changed = True
                    break
            else:
                out.append(box)
        merged = out
    return merged


def _prompt(resource_name: str, edits: list[TextEdit], wording_hint: str, strict: bool) -> str:
    mappings = []
    for edit in edits:
        jp = " ".join(str(edit.japanese).split())
        en = " ".join(str(edit.english).split())
        if jp and en:
            mappings.append(f"{jp} -> {en}")
    mapping_text = "; ".join(mappings)
    hint = " ".join(str(wording_hint).split())
    extra = ""
    if mapping_text:
        extra += f" Use these exact localization mappings: {mapping_text}."
    if hint:
        extra += f" Operator wording instruction: {hint}."
    if "roulette" in resource_name.lower() or "fortune" in resource_name.lower():
        extra += " Fortune labels: 大吉 = GREAT LUCK; 吉 = GOOD LUCK; 凶 = BAD LUCK."
    retry = (
        " This is a strict retry because a previous result left Japanese unchanged. "
        "Every targeted Japanese label must be visibly replaced with English."
        if strict else ""
    )
    return (
        "Perform a surgical localization edit on this original PlayStation 3 Sengoku BASARA 3 "
        "Utage UI sprite sheet. Preserve the native Capcom artwork. Do not redesign, recolor, "
        "restyle, move, resize, straighten, crop, add panels, add icons, add glow, or invent "
        "decoration. Keep borders, material, lighting, texture, perspective and ornament exactly "
        "as the source. Change only the visible Japanese/broken lettering that needs localization. "
        "The replacement English must look professionally integrated into the existing asset, "
        "matching its original weight, perspective, outline, bevel, wear and contrast. Keep every "
        "sprite in exactly the same atlas position. Do not add any unrelated words."
        + extra + retry
        + f" Resource: {resource_name!r}. Return the complete sprite sheet."
    )


def edit_texture(
    art_source: Image.Image,
    resource_name: str,
    api_key: str,
    *,
    edits: list[TextEdit] | None = None,
    wording_hint: str = "",
    strict: bool = False,
):
    if not api_key.strip():
        raise base.ImageEditError("No OpenAI API key supplied")
    art = art_source.convert("RGBA")
    edit_list = list(edits or [])
    canvas, placement = base._fit_canvas(art)
    generated = base._request(canvas, _prompt(resource_name, edit_list, wording_hint, strict), api_key)
    if generated.size != (base.WORK, base.WORK):
        generated = generated.resize((base.WORK, base.WORK), Image.Resampling.LANCZOS)
    x0, y0, x1, y1 = placement
    generated = generated.crop((x0, y0, x1, y1)).resize(art.size, Image.Resampling.LANCZOS)

    original = np.asarray(art, dtype=np.uint8)
    gen = np.asarray(generated.convert("RGBA"), dtype=np.uint8)
    out = original.copy()

    boxes = merged_edit_boxes(edit_list, art.size)
    if boxes:
        editable = np.zeros((art.height, art.width), dtype=bool)
        for box in boxes:
            editable[box.top:box.bottom, box.left:box.right] = True
        out[editable] = gen[editable]

        # Preserve the game's hidden RGB convention where both old and new are
        # fully transparent. New English glyph pixels are allowed to gain alpha.
        both_transparent = editable & (original[..., 3] <= 3) & (out[..., 3] <= 3)
        out[both_transparent, :3] = original[both_transparent, :3]
        edit_mode = "detected_text_regions_only"
    else:
        # No safe text geometry was detected. Keep the old V4 behaviour only as
        # a reviewable fallback, never as a silent write: geometry/size stay
        # fixed and transparent RGB is preserved.
        out[:] = gen
        transparent = original[..., 3] <= 3
        out[transparent, :3] = original[transparent, :3]
        edit_mode = "whole_sheet_no_regions"

    image = Image.fromarray(out, "RGBA")
    return image, {
        "mode": "v41_high_quality_ai_rebuild",
        "model": base.MODEL,
        "resource": resource_name,
        "edit_mode": edit_mode,
        "edit_boxes": [box.as_list() for box in boxes],
        "mappings": [
            {"box": edit.box.as_list(), "japanese": edit.japanese, "english": edit.english}
            for edit in edit_list
        ],
        "outside_edit_boxes_preserved": bool(boxes),
        "alpha_changes_allowed_inside_text_regions": bool(boxes),
        "transparent_rgb_preserved_where_still_transparent": True,
        "wording_hint": wording_hint or None,
        "strict_retry": strict,
    }
