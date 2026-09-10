from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")


def composite_and_grid(name: str, scale: int = 3) -> Path:
    source = Image.open(ROOT / f"{name}.png").convert("RGBA")
    background = Image.new("RGBA", source.size, (24, 31, 40, 255))
    image = Image.alpha_composite(background, source).convert("RGB")
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)

    margin = 82
    canvas = Image.new("RGB", (image.width + margin, image.height), (12, 16, 22))
    canvas.paste(image, (margin, 0))
    draw = ImageDraw.Draw(canvas)
    for source_y in range(0, source.height + 1, 32):
        y = source_y * scale
        color = (255, 205, 64) if source_y % 128 == 0 else (112, 130, 150)
        draw.line((margin, y, margin + image.width - 1, y), fill=color, width=1)
        draw.text((4, max(0, y - 7)), str(source_y), fill=color)

    target = ROOT / f"{name}_preview.png"
    canvas.save(target)
    return target


for atlas in (
    "cur_tenka_029",
    "cur_tenka_005",
    "cur_tenka_003",
    "cur_common_016",
    "sh_common_016",
    "sh_tenka_011",
    "sh_tenka_025",
):
    print(composite_and_grid(atlas))
