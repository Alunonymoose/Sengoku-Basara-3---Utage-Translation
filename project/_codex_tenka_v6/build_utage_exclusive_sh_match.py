from __future__ import annotations

"""Create SH-style candidates for Utage-only result labels.

The source English glyphs come from Utage's native English title resources.
Only their shape is retained; the SH donor set supplies the palette, internal
brush variation, outline, shadow, and highlight treatment. Candidates are
written outside the game tree until explicitly installed.
"""

import json
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arc_tools  # noqa: E402
from build_free_battle_v6 import decode_xet, patch_bc3_rect  # noqa: E402

ROOT = Path(r"E:\Utage Patching New")
RESULT = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
UTAGE_TITLE = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc"
SH_TITLE = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc")
OUT = HERE / "utage_exclusive_sh_match"
TARGETS = range(16, 30)
FONT = HERE / "fonts" / "KaushanScript-Regular.ttf"
NAMES = {
    16: "Muneshige Tachibana",
    17: "Hideaki Kobayakawa",
    18: "Yoshiaki Mogami",
    19: "Tenkai",
    20: "Kenshin Uesugi",
    21: "Kasuga",
    22: "Sasuke Sarutobi",
    23: "Kojiro Katakura",
    24: "Matsu",
    25: "Toshiie Maeda",
    26: "Ujimasa Hojo",
    27: "Shingen Takeda",
    28: "Hisahide Matsunaga",
    29: "Sorin Otomo",
}


def donor_images(path: Path) -> list[Image.Image]:
    archive = arc_tools.parse_arc(path)
    entries = [
        entry for entry in archive.entries
        if ("charasele_02_" in entry.name or "chara_se02_" in entry.name)
        and "_ID_HQ" in entry.name
        and "_qqq_" not in entry.name and "_lock_" not in entry.name
    ]
    entries.sort(key=lambda entry: int(entry.name.rsplit("_", 3)[1]))
    return [decode_xet(arc_tools.unpack(entry)).convert("RGBA") for entry in entries]


def fit_alpha(text: str, size: tuple[int, int]) -> Image.Image:
    if not FONT.exists():
        raise FileNotFoundError(FONT)
    canvas = Image.new("L", size, 0)
    draw = ImageDraw.Draw(canvas)
    for point_size in range(min(96, size[1] + 36), 10, -1):
        font = ImageFont.truetype(str(FONT), point_size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        if box[2] - box[0] <= size[0] - 24 and box[3] - box[1] <= size[1] - 16:
            x = (size[0] - (box[2] - box[0])) // 2 - box[0]
            y = (size[1] - (box[3] - box[1])) // 2 - box[1]
            draw.text((x, y), text, font=font, fill=255, stroke_width=1, stroke_fill=255)
            return canvas
    raise ValueError(f"text does not fit {size}: {text}")


def sh_profile(
    images: list[Image.Image],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pixels: list[np.ndarray] = []
    alpha_rows: list[np.ndarray] = []
    for image in images:
        rgba = np.asarray(image)
        alpha = rgba[:, :, 3]
        pixels.append(rgba[alpha > 32, :3])
        alpha_rows.append(alpha.mean(axis=1))
    colors = np.concatenate(pixels).astype(np.float32)
    # The result-screen SH lettering is ivory with warm brown edging. The
    # title-screen green donors are a different UI treatment and must not
    # determine this palette.
    bright = np.array([248, 244, 222], dtype=np.float32)
    mid = np.array([224, 207, 167], dtype=np.float32)
    dark = np.array([74, 48, 27], dtype=np.float32)
    rows = np.mean(alpha_rows, axis=0)
    rows = cv2.resize(rows[:, None], (1, 128), interpolation=cv2.INTER_CUBIC)[:, 0]
    rows = (rows - rows.min()) / max(1.0, rows.max() - rows.min())
    return bright, mid, dark, rows


def brush_render(mask: Image.Image, profile: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], seed: int) -> Image.Image:
    bright, mid, dark, row_profile = profile
    width, height = mask.size
    mask_array = np.asarray(mask, dtype=np.float32)
    rng = np.random.default_rng(seed)

    # Low-frequency variation gives the clean Utage glyph mask the uneven
    # pigment density visible in the SH originals.
    noise = rng.random((height, width), dtype=np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), 2.4)
    noise = 0.78 + 0.30 * noise
    rows = np.interp(np.linspace(0, 127, height), np.arange(128), row_profile)
    coverage = np.clip(mask_array * noise * (0.90 + rows[:, None] * 0.10), 0, 255).astype(np.uint8)

    # Use a second independent field for sparse dry-brush transparency.
    speck = rng.random((height, width), dtype=np.float32)
    coverage[(speck > 0.997) & (coverage > 80)] = 0

    t = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    rgb = bright[None, None, :] * (1 - t) + mid[None, None, :] * t
    rgb = rgb * 0.90 + dark[None, None, :] * 0.10
    body = np.zeros((height, width, 4), dtype=np.uint8)
    body[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    body[:, :, 3] = coverage

    base = Image.fromarray(body, "RGBA")
    dilated = mask.filter(ImageFilter.MaxFilter(9))
    shadow_mask = dilated.filter(ImageFilter.GaussianBlur(0.7))
    shadow = Image.new("RGBA", (width, height), tuple(np.clip(dark * 0.62, 0, 255).astype(int)) + (0,))
    shadow.putalpha(shadow_mask.point(lambda value: min(220, value)))

    outline = Image.new("RGBA", (width, height), tuple(np.clip(dark * 0.78, 0, 255).astype(int)) + (0,))
    outline.putalpha(dilated)

    # A narrow pale offset highlight is characteristic of the SH lettering.
    highlight_mask = ImageChops.subtract(mask, mask.filter(ImageFilter.GaussianBlur(1.2)))
    highlight_mask = ImageChops.offset(highlight_mask, -1, -1)
    highlight = Image.new("RGBA", (width, height), (255, 252, 232, 0))
    highlight.putalpha(highlight_mask.point(lambda value: min(95, value)))

    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.alpha_composite(shadow, (3, 4))
    result.alpha_composite(outline)
    result.alpha_composite(base)
    result.alpha_composite(highlight)
    return result


def patch(raw: bytes, text: str, profile, seed: int) -> tuple[bytes, Image.Image]:
    target = decode_xet(raw).convert("RGBA")
    mask = fit_alpha(text, target.size)
    rendered = brush_render(mask, profile, seed)
    return patch_bc3_rect(raw, rendered, (0, 0, target.width, target.height)), rendered


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    utage = donor_images(UTAGE_TITLE)
    sh = donor_images(SH_TITLE)
    if len(utage) != 30 or len(sh) < 16:
        raise RuntimeError(f"unexpected donor counts: Utage={len(utage)}, SH={len(sh)}")
    profile = sh_profile(sh[:16])
    report = {"status": "pass", "archives": [], "changed_entries": [2, 4]}
    for number in TARGETS:
        source_archive = RESULT / f"pl{number:03}.arc"
        candidate_archive = OUT / source_archive.name
        archive = arc_tools.parse_arc(source_archive)
        replacements = {}
        previews = {}
        for index in (2, 4):
            replacements[index], previews[index] = patch(
                arc_tools.unpack(archive.entries[index]), NAMES[number], profile, number * 31 + index
            )
            previews[index].save(OUT / f"pl{number:03}_entry_{index}.png")
        candidate_archive.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(candidate_archive)
        for index, expected in ((2, (256, 128)), (4, (1024, 128))):
            decoded = decode_xet(arc_tools.unpack(verified.entries[index]))
            if decoded.size != expected:
                raise AssertionError(f"{candidate_archive.name} entry {index}: {decoded.size}")
        report["archives"].append({
            "archive": source_archive.name,
            "candidate": str(candidate_archive),
            "changed_entries": [2, 4],
        })
    manifest = OUT / "SH_MATCH_CANDIDATE.json"
    manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "candidate_archives": len(report["archives"]), "output": str(OUT)}))


if __name__ == "__main__":
    main()
