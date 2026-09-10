from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect


ROOT = Path(r"E:\Utage Patching New")
RESULT_DIR = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
WORK_DIR = ROOT / r"_codex_tenka_v6"
FONT = r"C:\Windows\Fonts\arialbd.ttf"

LABELS = {
    0: "Date Army",
    1: "Takeda Army",
    2: "Ishida Army",
    3: "Tokugawa Army",
    4: "Saika Army",
    5: "Kuroda Army",
    6: "Uesugi Army",
    7: "Iyo Kono Army",
    8: "Hojo Army",
    9: "Chosokabe Army",
    10: "Ishida Army",
    11: "Shimazu Army",
    12: "Oda Remnants",
    13: "Mori Army",
    14: "Tokugawa Army",
    15: "Oda Army",
    16: "Otomo Army",
    17: "Kobayakawa Army",
    18: "Mogami Army",
    19: "Kobayakawa Army",
    20: "Uesugi Army",
    21: "Uesugi Army",
    22: "Takeda Army",
    23: "Date Army",
    24: "Maeda Army",
    25: "Maeda Army",
    26: "Hojo Army",
    27: "Takeda Army",
    28: "Matsunaga Army",
    29: "Otomo Army",
}


def render_label(text: str, size: tuple[int, int]) -> object:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for font_size in range(30, 7, -1):
        font = ImageFont.truetype(FONT, font_size)
        box = draw.textbbox((0, 0), text, font=font)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= size[0] - 8 and height <= size[1] - 8:
            x = (size[0] - width) // 2 - box[0]
            y = (size[1] - height) // 2 - box[1]
            draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 180))
            draw.text((x, y), text, font=font, fill=(123, 255, 123, 255))
            return canvas
    raise ValueError(f"label does not fit: {text!r}")


def main() -> None:
    report: list[dict[str, object]] = []
    for number, label in LABELS.items():
        path = RESULT_DIR / f"pl{number:03}.arc"
        archive = arc_tools.parse_arc(path)
        entry = archive.entries[6]
        original = arc_tools.unpack(entry)
        image = decode_xet(original)
        if image.size != (256, 64):
            raise ValueError(f"{path.name}: unexpected army texture size {image.size}")
        image.paste((0, 0, 0, 0), (0, 0, 256, 64))
        image.alpha_composite(render_label(label, image.size), (0, 0))
        replacement = patch_bc3_rect(original, image, (0, 0, 256, 64))
        rebuilt = arc_tools.rebuild(archive, {6: replacement})
        path.write_bytes(rebuilt)
        verified = arc_tools.parse_arc(path)
        verified_raw = arc_tools.unpack(verified.entries[6])
        if verified_raw != replacement:
            raise AssertionError(f"{path.name}: rebuilt texture mismatch")
        preview = decode_xet(verified_raw)
        preview.save(WORK_DIR / f"result_{number:03}_army_english.png")
        report.append(
            {
                "archive": str(path),
                "resource": entry.name,
                "label": label,
                "dimensions": list(image.size),
                "format": "BC3/DXT5",
                "changed_entry": 6,
            }
        )
    (WORK_DIR / "RESULT_ARMY_TEXTURE_REPLACEMENT_REPORT.json").write_text(
        json.dumps({"status": "pass", "replacements": report}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "archives": len(report)}, indent=2))


if __name__ == "__main__":
    main()
