from __future__ import annotations

from PIL import ImageDraw, ImageFont

import build_free_battle_v6 as base


FONT = r"C:\Windows\Fonts\arialbd.ttf"


def render_label(text: str, size: tuple[int, int], max_font: int):
    canvas = base.Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for font_size in range(max_font, 7, -1):
        font = ImageFont.truetype(FONT, font_size)
        box = draw.textbbox((0, 0), text, font=font)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= size[0] - 2 and height <= size[1] - 2:
            x = (size[0] - width) // 2 - box[0]
            y = (size[1] - height) // 2 - box[1]
            draw.text((x + 1, y + 1), text, font=font, fill=(123, 255, 123, 120))
            draw.text((x, y), text, font=font, fill=(123, 255, 123, 255))
            return canvas
    raise ValueError(f"label does not fit: {text!r} in {size}")


def edit_top_label(target_raw: bytes, donor_raw: bytes):
    target = base.decode_xet(target_raw)
    clear_rect = (672, 96, 824, 128)
    base.clear(target, clear_rect)
    target.alpha_composite(render_label("Quick Battles", (148, 28), 22), (674, 98))
    edited = base.patch_bc3_rect(target_raw, target, clear_rect)
    base.decode_xet(edited).save(base.ROOT / "v6_top_quick_battles_preview.png")
    return edited, {
        "resource": "id\\texture\\jpn\\tenka\\tenka_005_ID_HQ",
        "change": "Free Battle header: Japanese -> Quick Battles",
        "target_rect_physical": list(clear_rect),
        "rendered_label_size": [148, 28],
        "source": "official Samurai Heroes terminology; Arial Bold raster for BC3 legibility",
    }


def edit_battle_suffix(target_raw: bytes, donor_raw: bytes):
    target = base.decode_xet(target_raw)
    clear_rect = (96, 0, 180, 64)
    base.clear(target, clear_rect)
    target.alpha_composite(render_label("Battles", (82, 40), 24), (97, 12))
    edited = base.patch_bc3_rect(target_raw, target, clear_rect)
    base.decode_xet(edited).save(base.ROOT / "v6_battles_suffix_preview.png")
    return edited, {
        "resource": "id\\texture\\jpn\\tenka\\tenka_029_ID_HQ",
        "change": "Battle count suffix: Japanese -> Battles",
        "target_rect_physical": list(clear_rect),
        "rendered_label_size": [82, 40],
        "source": "official Samurai Heroes terminology; Arial Bold raster for BC3 legibility",
    }


if __name__ == "__main__":
    base.edit_top_label = edit_top_label
    base.edit_battle_suffix = edit_battle_suffix
    base.main()
