from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect


ROOT = Path(r"E:\Utage Patching New")
RESULT_DIR = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
SH_TITLE = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc")
WORK_DIR = ROOT / r"_codex_tenka_v6"


def donor_image(title: arc_tools.Archive, index: int) -> Image.Image:
    return decode_xet(arc_tools.unpack(title.entries[index]))


def build_texture(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    alpha_box = source.getchannel("A").getbbox()
    if alpha_box is None:
        raise ValueError("Samurai Heroes donor has no visible pixels")
    left, top, right, bottom = alpha_box
    margin = 18
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(source.width, right + margin)
    bottom = min(source.height, bottom + margin)
    crop = source.crop((left, top, right, bottom))
    target = Image.new("RGBA", size, (0, 0, 0, 0))
    scale = min((size[0] - 12) / crop.width, (size[1] - 8) / crop.height)
    resized = crop.resize(
        (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
        Image.Resampling.LANCZOS,
    )
    target.alpha_composite(
        resized,
        ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2),
    )
    return target


def replace(original: bytes, donor: Image.Image) -> bytes:
    target = decode_xet(original)
    rendered = build_texture(donor, target.size)
    return patch_bc3_rect(original, rendered, (0, 0, target.width, target.height))


def main() -> None:
    title = arc_tools.parse_arc(SH_TITLE)
    report = []
    donor_map = {number: 41 + number for number in range(16)}
    for number, donor_index in donor_map.items():
        path = RESULT_DIR / f"pl{number:03}.arc"
        archive = arc_tools.parse_arc(path)
        donor = donor_image(title, donor_index)
        replacements = {
            2: replace(arc_tools.unpack(archive.entries[2]), donor),
            4: replace(arc_tools.unpack(archive.entries[4]), donor),
        }
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        for index in replacements:
            raw = arc_tools.unpack(verified.entries[index])
            decode_xet(raw).save(WORK_DIR / f"sh_result_{number:03}_entry_{index}.png")
        report.append(
            {
                "archive": str(path),
                "donor": f"{SH_TITLE} entry {donor_index}",
                "changed_entries": [2, 4],
            }
        )
    (WORK_DIR / "SH_RESULT_DONOR_TRANSPLANT_REPORT.json").write_text(
        json.dumps({"status": "pass", "replacements": report}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "archives": len(report)}))


if __name__ == "__main__":
    main()
