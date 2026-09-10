"""Finish the Utage result-name textures without touching pause or other archives.

The lettering is rendered from the same green brush treatment found in the
Samurai Heroes English title textures.  The XET/BC3 container is never rebuilt:
only its decoded rectangle is replaced, so dimensions and mip/layout metadata
remain those of each result archive.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect

ROOT = Path(r"E:\Utage Patching New")
RESULT = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
SH_TITLE = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc")
OUT = ROOT / r"_codex_tenka_v6\result_remaining"
FONT = r"C:\Windows\Fonts\Inkfree.ttf"

NAMES = {
    4: "Toshiie Maeda", 6: "Kenshin Uesugi", 7: "Naotora Ii",
    16: "Muneshige Tachibana", 17: "Hideaki Kobayakawa",
    18: "Yoshiaki Mogami", 19: "Tenkai", 20: "Kenshin Uesugi",
    21: "Kasuga", 22: "Sasuke Sarutobi", 23: "Kojiro Katakura",
    24: "Matsu", 25: "Toshiie Maeda", 26: "Ujiyasu Hojo",
    27: "Shingen Takeda", 28: "Hisahide Matsunaga", 29: "Sorin Otomo",
}
TARGET_ENTRIES = (2, 4)


def donor_style() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Read actual SH title pixels, rather than assuming a system-font palette."""
    arc = arc_tools.parse_arc(SH_TITLE)
    pixels = []
    for entry in arc.entries:
        if "\\eng\\chara_se02\\" in entry.name:
            image = decode_xet(arc_tools.unpack(entry)).convert("RGBA")
            pixels.extend(p for p in image.getdata() if p[3] > 100)
    if not pixels:
        raise RuntimeError("no Samurai Heroes English title donors found")
    pixels.sort(key=lambda p: p[1] - p[0], reverse=True)
    bright = pixels[len(pixels) // 4]
    dark = tuple(max(0, int(c * 0.16)) for c in bright[:3])
    return bright[:3], dark


def render_brush(text: str, size: tuple[int, int], bright, dark) -> Image.Image:
    """Render a rough, layered brush treatment based on the SH title lettering."""
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # Inkfree supplies the handwritten skeleton; SH donor colors, heavy edge,
    # offset ink, and deterministic dry-brush breakup provide the actual style.
    for point in range(82, 16, -1):
        font = ImageFont.truetype(FONT, point)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        w, h = box[2] - box[0], box[3] - box[1]
        if w <= size[0] - 28 and h <= size[1] - 20:
            x = (size[0] - w) // 2 - box[0]
            y = (size[1] - h) // 2 - box[1]
            break
    else:
        raise ValueError(f"text does not fit {size}: {text}")
    # A dark, offset ink edge and bright green body match the SH result/title
    # treatment much more closely than a plain font fill.
    draw.text((x + 3, y + 4), text, font=font, fill=(*dark, 220),
              stroke_width=6, stroke_fill=(*dark, 220))
    draw.text((x, y), text, font=font, fill=(*bright, 255),
              stroke_width=3, stroke_fill=(*dark, 255))
    # Dry brush: sparse alpha loss, softened so BC3 retains natural edges.
    rng = random.Random(text)
    noise = Image.new("L", size, 255)
    nd = ImageDraw.Draw(noise)
    for _ in range(max(20, size[0] // 3)):
        px = rng.randrange(size[0]); py = rng.randrange(size[1])
        nd.ellipse((px, py, px + rng.randrange(1, 8), py + rng.randrange(1, 4)),
                   fill=rng.randrange(170, 245))
    noise = noise.filter(ImageFilter.GaussianBlur(0.45))
    alpha = canvas.getchannel("A")
    alpha = Image.composite(alpha, Image.new("L", size, 0), noise)
    canvas.putalpha(alpha)
    return canvas


def replace(raw: bytes, text: str, bright, dark) -> tuple[bytes, Image.Image]:
    original = decode_xet(raw).convert("RGBA")
    rendered = render_brush(text, original.size, bright, dark)
    return patch_bc3_rect(raw, rendered, (0, 0, *original.size)), rendered


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bright, dark = donor_style()
    report = {"status": "pass", "donor": str(SH_TITLE), "archives": []}
    previews = []
    for number, text in NAMES.items():
        path = RESULT / f"pl{number:03}.arc"
        archive = arc_tools.parse_arc(path)
        replacements = {}
        for index in TARGET_ENTRIES:
            replacements[index], preview = replace(
                arc_tools.unpack(archive.entries[index]), text, bright, dark
            )
            preview.save(OUT / f"pl{number:03}_entry_{index}.png")
            previews.append((number, index, preview))
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        dims = [list(decode_xet(arc_tools.unpack(verified.entries[i])).size)
                for i in TARGET_ENTRIES]
        if dims != [[256, 128], [1024, 128]]:
            raise AssertionError(f"pl{number:03}: unexpected XET dimensions {dims}")
        report["archives"].append({"archive": str(path), "name": text,
                                   "changed_entries": list(TARGET_ENTRIES),
                                   "dimensions": dims})
    # Contact sheet is deliberately outside the game tree.
    thumb_w, thumb_h = 256, 64
    sheet = Image.new("RGBA", (thumb_w * 4, (len(previews) + 3) // 4 * 92),
                      (35, 35, 35, 255))
    sd = ImageDraw.Draw(sheet)
    for n, (number, index, image) in enumerate(previews):
        thumb = image.copy(); thumb.thumbnail((thumb_w - 8, thumb_h - 8))
        x = (n % 4) * thumb_w + 4; y = (n // 4) * 92 + 18
        sheet.alpha_composite(thumb, (x, y))
        sd.text((x, y - 16), f"pl{number:03} / {index}", fill=(230, 230, 230))
    sheet.save(OUT / "remaining_result_contact_sheet.png")
    # Validate every archive, not merely the files changed above.
    all_archives = sorted(RESULT.glob("pl*.arc"))
    if len(all_archives) != 30:
        raise AssertionError(f"expected 30 result archives, found {len(all_archives)}")
    for path in all_archives:
        archive = arc_tools.parse_arc(path)
        for index in TARGET_ENTRIES:
            if decode_xet(arc_tools.unpack(archive.entries[index])).size not in ((256, 128), (1024, 128)):
                raise AssertionError(f"{path.name}: invalid result texture")
    report["generated_resources"] = [
        *(f"pl{number:03}_entry_{index}.png" for number, index, _ in previews),
        "remaining_result_contact_sheet.png",
    ]
    report["scope"] = {
        "modified_game_files": [
            f"PS3_GAME\\USRDIR\\nativePS3\\rom\\eng\\result\\pl{number:03}.arc"
            for number in NAMES
        ],
        "modified_entries": "entry 2 (256x128 name) and entry 4 (1024x128 result title)",
        "excluded": ["pause archives", "non-result archives"],
    }
    (OUT / "VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "changed_archives": len(NAMES),
                      "validated_archives": len(all_archives), "entries_per_archive": 2}))


if __name__ == "__main__":
    main()
