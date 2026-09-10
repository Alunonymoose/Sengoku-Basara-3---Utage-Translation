from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arc_tools  # noqa: E402
from build_free_battle_v6 import decode_xet, patch_bc3_rect  # noqa: E402

ROOT = Path(r"E:\Utage Patching New")
ENG = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng"
OUT = ROOT / r"_codex_tenka_v6\tenka_japmap_11_fix"
FONT = Path(r"C:\Windows\Fonts\arialbi.ttf")
TEXT = "WINNING BET!"


def render(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for point_size in range(150, 20, -1):
        font = ImageFont.truetype(str(FONT), point_size)
        box = draw.textbbox((0, 0), TEXT, font=font, stroke_width=1)
        if box[2] - box[0] <= size[0] - 110 and box[3] - box[1] <= size[1] - 60:
            x = (size[0] - (box[2] - box[0])) // 2 - box[0]
            y = (size[1] - (box[3] - box[1])) // 2 - box[1]
            draw.text(
                (x + 3, y + 4),
                TEXT,
                font=font,
                fill=(34, 75, 36, 210),
                stroke_width=7,
                stroke_fill=(34, 75, 36, 210),
            )
            draw.text(
                (x, y),
                TEXT,
                font=font,
                fill=(250, 250, 250, 255),
                stroke_width=4,
                stroke_fill=(38, 98, 43, 255),
            )
            return image
    raise ValueError("WINNING BET! does not fit")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    candidate = render((1024, 256))
    candidate.save(OUT / "tenka_japmap_11_candidate.png")
    report = {"status": "pass", "text": TEXT, "archives": [], "changed_entries": []}
    for path in sorted(ENG.rglob("*.arc")):
        archive = arc_tools.parse_arc(path)
        replacements = {}
        for entry in archive.entries:
            if "tenka_japmap_11_ID_HQ" not in entry.name:
                continue
            original = arc_tools.unpack(entry)
            target = decode_xet(original)
            if target.size != (1024, 256):
                raise ValueError(f"{path}: unexpected size {target.size}")
            replacements[entry.index] = patch_bc3_rect(original, candidate, (0, 0, 1024, 256))
        if not replacements:
            continue
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        for index in replacements:
            decoded = decode_xet(arc_tools.unpack(verified.entries[index]))
            if decoded.size != (1024, 256):
                raise AssertionError(f"{path}: invalid decoded size")
        report["archives"].append({"archive": str(path), "entries": sorted(replacements)})
        report["changed_entries"].extend(
            {"archive": str(path), "entry": index} for index in replacements
        )
    report["archive_count"] = len(report["archives"])
    report["resource_count"] = len(report["changed_entries"])
    (OUT / "TENKA_JAPMAP_11_FIX_REPORT.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": "pass",
        "archives": report["archive_count"],
        "resources": report["resource_count"],
        "preview": str(OUT / "tenka_japmap_11_candidate.png"),
    }))


if __name__ == "__main__":
    main()
