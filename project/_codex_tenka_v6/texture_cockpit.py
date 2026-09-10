from __future__ import annotations

"""Create a reproducible visual audit of result ARC textures.

This is intentionally read-only with respect to game archives. It extracts the
candidate label textures, writes PNG previews/contact sheets, and records
dimensions, alpha coverage, perceptual hashes, and archive hashes in JSON.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arc_tools  # noqa: E402
from build_free_battle_v6 import decode_xet, xet_info  # noqa: E402


def alpha_coverage(image: Image.Image) -> float:
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    return float(np.count_nonzero(alpha >= 16) / alpha.size)


def edge_density(image: Image.Image) -> float:
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return float(np.count_nonzero(edges) / edges.size)


def font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("segoeui.ttf", 16)
    except OSError:
        return ImageFont.load_default()


def make_contact_sheet(images: list[tuple[str, Image.Image]], output: Path) -> None:
    if not images:
        return
    tile_width = 512
    tile_height = 112
    label_height = 28
    columns = 2
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + label_height)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    label_font = font()
    for index, (label, image) in enumerate(images):
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + label_height)
        preview = image.convert("RGBA")
        preview.thumbnail((tile_width - 8, tile_height - 8), Image.Resampling.NEAREST)
        px = x + (tile_width - preview.width) // 2
        py = y + (tile_height - preview.height) // 2
        sheet.paste(preview, (px, py), preview)
        draw.text((x + 6, y + tile_height + 4), label, fill=(230, 230, 230), font=label_font)
    sheet.save(output)


def audit(result_dir: Path, output_dir: Path, entry_indices: list[int]) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"status": "pass", "source": str(result_dir), "archives": []}
    for path in sorted(result_dir.glob("pl*.arc")):
        archive = arc_tools.parse_arc(path)
        record = {
            "archive": path.name,
            "archive_sha256": arc_tools.sha256(path.read_bytes()),
            "entry_count": len(archive.entries),
            "textures": [],
        }
        for index in entry_indices:
            entry = archive.entries[index]
            raw = arc_tools.unpack(entry)
            info = xet_info(raw)
            image = decode_xet(raw)
            preview_name = f"{path.stem}_entry_{index}.png"
            image.save(output_dir / preview_name)
            record["textures"].append(
                {
                    "entry": index,
                    "name": entry.name,
                    "dimensions": [info["width"], info["height"]],
                    "format": info["fourcc"],
                    "alpha_coverage": round(alpha_coverage(image), 6),
                    "edge_density": round(edge_density(image), 6),
                    "phash": str(imagehash.phash(image.convert("RGB"))),
                    "preview": preview_name,
                }
            )
        manifest["archives"].append(record)

    for index in entry_indices:
        images = []
        for record in manifest["archives"]:
            texture = next(item for item in record["textures"] if item["entry"] == index)
            images.append(
                (
                    f"{record['archive']}  {texture['name']}",
                    Image.open(output_dir / texture["preview"]).convert("RGBA"),
                )
            )
        make_contact_sheet(images, output_dir / f"contact_entry_{index}.png")
    manifest["archive_count"] = len(manifest["archives"])
    manifest["texture_count"] = sum(len(item["textures"]) for item in manifest["archives"])
    (output_dir / "TEXTURE_COCKPIT.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng\result"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "texture_cockpit",
    )
    parser.add_argument("--entries", type=int, nargs="+", default=[2, 4])
    args = parser.parse_args()
    result = audit(args.result_dir, args.output_dir, args.entries)
    print(json.dumps({
        "status": result["status"],
        "archives": result["archive_count"],
        "textures": result["texture_count"],
        "output": str(args.output_dir),
    }))


if __name__ == "__main__":
    main()
