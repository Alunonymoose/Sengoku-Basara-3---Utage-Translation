from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect


ROOT = Path(r"E:\Utage Patching New")
RESULT_DIR = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
TITLE_ARC = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc"
WORK_DIR = ROOT / r"_codex_tenka_v6"
FONT = r"C:\Windows\Fonts\Inkfree.ttf"

NAMES = {
    0: "Masamune Date",
    1: "Yukimura Sanada",
    2: "Mitsunari Ishida",
    3: "Ieyasu Tokugawa",
    4: "Toshiie Maeda",
    5: "Kanbei Kuroda",
    6: "Kenshin Uesugi",
    7: "Naotora Ii",
    8: "Kotaro Fuma",
    9: "Motochika Chosokabe",
    10: "Yoshitsugu Otani",
    11: "Yoshihiro Shimazu",
    12: "Oichi",
    13: "Motonari Mori",
    14: "Tadakatsu Honda",
    15: "Nobunaga Oda",
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
    26: "Ujiyasu Hojo",
    27: "Shingen Takeda",
    28: "Hisahide Matsunaga",
    29: "Sorin Otomo",
}


def render_name(text: str, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for font_size in range(58, 15, -1):
        font = ImageFont.truetype(FONT, font_size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= size[0] - 12 and height <= size[1] - 12:
            x = (size[0] - width) // 2 - box[0]
            y = (size[1] - height) // 2 - box[1]
            draw.text((x + 2, y + 3), text, font=font, fill=(5, 12, 5, 220),
                      stroke_width=4, stroke_fill=(5, 12, 5, 220))
            draw.text((x, y), text, font=font, fill=(128, 255, 92, 255),
                      stroke_width=2, stroke_fill=(16, 38, 14, 255))
            return canvas
    raise ValueError(f"name does not fit: {text!r}")


def render_charasele(text: str, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for font_size in range(62, 15, -1):
        font = ImageFont.truetype(FONT, font_size)
        box = draw.textbbox((0, 0), text, font=font)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= size[0] - 24 and height <= size[1] - 12:
            x = (size[0] - width) // 2 - box[0]
            y = (size[1] - height) // 2 - box[1]
            draw.text((x + 2, y + 3), text, font=font, fill=(4, 12, 4, 220),
                      stroke_width=4, stroke_fill=(4, 12, 4, 220))
            draw.text((x, y), text, font=font, fill=(128, 255, 92, 255),
                      stroke_width=2, stroke_fill=(16, 38, 14, 255))
            return canvas
    raise ValueError(f"character-select name does not fit: {text!r}")


def generated_name(original: bytes, text: str) -> bytes:
    image = decode_xet(original)
    image.paste((0, 0, 0, 0), (0, 0, image.width, image.height))
    image.alpha_composite(render_name(text, image.size), (0, 0))
    return patch_bc3_rect(original, image, (0, 0, image.width, image.height))


def generated_charasele(donor: bytes, text: str) -> bytes:
    image = decode_xet(donor)
    image.paste((0, 0, 0, 0), (0, 0, image.width, image.height))
    image.alpha_composite(render_charasele(text, image.size), (0, 0))
    return patch_bc3_rect(donor, image, (0, 0, image.width, image.height))


def main() -> None:
    title = arc_tools.parse_arc(TITLE_ARC)
    title_charasele = {
        Path(entry.name.replace("\\", "/")).name: arc_tools.unpack(entry)
        for entry in title.entries
        if "charasele_02" in entry.name
    }
    report = []
    for number, name in NAMES.items():
        path = RESULT_DIR / f"pl{number:03}.arc"
        archive = arc_tools.parse_arc(path)
        name_entry = archive.entries[2]
        charasele_entry = archive.entries[4]
        basename = Path(charasele_entry.name.replace("\\", "/")).name
        donor = title_charasele.get(basename)
        if donor is None:
            raise KeyError(f"missing verified title donor: {basename}")
        if len(donor) != charasele_entry.raw_size:
            raise ValueError(f"{basename}: donor size mismatch")
        replacements = {
            2: generated_name(arc_tools.unpack(name_entry), name),
            4: generated_charasele(donor, name),
        }
        rebuilt = arc_tools.rebuild(archive, replacements)
        path.write_bytes(rebuilt)
        verified = arc_tools.parse_arc(path)
        for index in replacements:
            raw = arc_tools.unpack(verified.entries[index])
            decode_xet(raw).save(WORK_DIR / f"result_{number:03}_entry_{index}_english.png")
        report.append(
            {
                "archive": str(path),
                "name": name,
                "changed_entries": [2, 4],
                "charasele_donor": str(TITLE_ARC),
            }
        )
    (WORK_DIR / "RESULT_NAME_TEXTURE_REPLACEMENT_REPORT.json").write_text(
        json.dumps({"status": "pass", "replacements": report}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "archives": len(report), "entries_per_archive": 2}))


if __name__ == "__main__":
    main()
