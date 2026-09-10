from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect

ROOT = Path(r"E:\Utage Patching New")
RESULT = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
DONOR = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc")
OUT = ROOT / r"_codex_tenka_v6\result_donor_v2"
FONT = r"C:\Windows\Fonts\segoeprb.ttf"
NAMES = {
    0: "Masamune Date", 1: "Yukimura Sanada", 2: "Mitsunari Ishida",
    3: "Ieyasu Tokugawa", 4: "Toshiie Maeda", 5: "Kanbei Kuroda",
    6: "Kenshin Uesugi", 7: "Naotora Ii", 8: "Kotaro Fuma",
    9: "Motochika Chosokabe", 10: "Yoshitsugu Otani", 11: "Yoshihiro Shimazu",
    12: "Oichi", 13: "Motonari Mori", 14: "Tadakatsu Honda", 15: "Nobunaga Oda",
    16: "Muneshige Tachibana", 17: "Hideaki Kobayakawa", 18: "Yoshiaki Mogami",
    19: "Tenkai", 20: "Kenshin Uesugi", 21: "Kasuga", 22: "Sasuke Sarutobi",
    23: "Kojiro Katakura", 24: "Matsu", 25: "Toshiie Maeda", 26: "Ujiyasu Hojo",
    27: "Shingen Takeda", 28: "Hisahide Matsunaga", 29: "Sorin Otomo",
}


def donor_profile(images):
    fg = []
    rows = []
    for im in images:
        a = np.asarray(im.convert("RGBA"))
        alpha = a[:, :, 3]
        visible = alpha > 32
        fg.extend(a[visible, :3].tolist())
        rows.append(alpha.astype(np.float32).mean(axis=1))
    fg = np.asarray(fg, dtype=np.float32)
    # Percentiles and vertical profile are measured from the actual SH title pixels.
    bright = np.percentile(fg, 78, axis=0)
    dark = np.percentile(fg, 18, axis=0) * 0.48
    profile = np.mean(rows, axis=0)
    profile = cv2.resize(profile[:, None], (1, 128), interpolation=cv2.INTER_LINEAR)[:, 0]
    profile = (profile - profile.min()) / max(1, profile.max() - profile.min())
    return bright, dark, profile


def fit_font(text, size):
    d = ImageDraw.Draw(Image.new("L", size))
    for n in range(min(96, size[1] + 40), 12, -1):
        f = ImageFont.truetype(FONT, n)
        b = d.textbbox((0, 0), text, font=f, stroke_width=1)
        if b[2] - b[0] <= size[0] - 24 and b[3] - b[1] <= size[1] - 12:
            return f, b
    raise ValueError(text)


def render(text, size, profile, bright, dark, seed):
    f, box = fit_font(text, size)
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    x = (size[0] - (box[2] - box[0])) // 2 - box[0]
    y = (size[1] - (box[3] - box[1])) // 2 - box[1]
    d.text((x, y), text, font=f, fill=255, stroke_width=1, stroke_fill=255)
    m = np.asarray(mask, dtype=np.uint8)
    rng = np.random.default_rng(seed)
    # Actual SH alpha profile drives the vertical ink modulation; OpenCV adds
    # low-frequency dry-brush breakup without retaining donor glyph silhouettes.
    noise = rng.integers(0, 256, (size[1], size[0]), dtype=np.uint8)
    noise = cv2.GaussianBlur(noise, (0, 0), 2.1).astype(np.float32) / 255.0
    noise = 0.78 + 0.30 * noise
    row = np.interp(np.linspace(0, 127, size[1]), np.arange(128), profile)
    coverage = np.clip(m.astype(np.float32) * (0.86 + 0.14 * row[:, None]) * noise, 0, 255).astype(np.uint8)
    body = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    t = np.linspace(0, 1, size[1], dtype=np.float32)[:, None]
    rgb = bright[None, None, :] * (1 - t[:, :, None]) + dark[None, None, :] * t[:, :, None]
    body[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    body[:, :, 3] = coverage
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    edge = mask.filter(ImageFilter.MaxFilter(9))
    shadow = Image.new("RGBA", size, tuple(np.clip(dark, 0, 255).astype(int)) + (228,))
    shadow.putalpha(edge)
    out.alpha_composite(shadow, (3, 4))
    outline = Image.new("RGBA", size, tuple(np.clip(dark * 0.72, 0, 255).astype(int)) + (255,))
    outline.putalpha(edge)
    out.alpha_composite(outline)
    out.alpha_composite(Image.fromarray(body, "RGBA"))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    title = arc_tools.parse_arc(DONOR)
    donors = [decode_xet(arc_tools.unpack(title.entries[41 + i])).convert("RGBA") for i in range(16)]
    bright, dark, profile = donor_profile(donors)
    previews = []
    report = {"status": "pass", "donor": str(DONOR),
              "method": "SH-derived palette, alpha profile, gradient, outline, shadow, and OpenCV dry-brush modulation",
              "limitations": "Letter skeletons remain newly composed English glyphs; no exact SH donor exists for most remaining names."}
    for n, text in NAMES.items():
        path = RESULT / f"pl{n:03}.arc"
        arc = arc_tools.parse_arc(path)
        repl = {}
        for idx in (2, 4):
            raw = arc_tools.unpack(arc.entries[idx])
            base = decode_xet(raw).convert("RGBA")
            image = render(text, base.size, profile, bright, dark, n * 100 + idx)
            repl[idx] = patch_bc3_rect(raw, image, (0, 0, *base.size))
            image.save(OUT / f"pl{n:03}_entry_{idx}.png")
            previews.append((n, idx, image))
        path.write_bytes(arc_tools.rebuild(arc, repl))
    sheet = Image.new("RGBA", (520, ((len(previews) + 3) // 4) * 86), (28, 28, 28, 255))
    sd = ImageDraw.Draw(sheet)
    for i, (n, idx, im) in enumerate(previews):
        thumb = im.copy(); thumb.thumbnail((126, 64))
        x, y = (i % 4) * 130, (i // 4) * 86 + 18
        sheet.alpha_composite(thumb, (x, y)); sd.text((x, y - 15), f"pl{n:03}/{idx}", fill="white")
    sheet.save(OUT / "result_donor_v2_contact_sheet.png")
    archives = sorted(RESULT.glob("pl*.arc"))
    assert len(archives) == 30
    for path in archives:
        a = arc_tools.parse_arc(path)
        for idx, expected in ((2, (256, 128)), (4, (1024, 128))):
            raw = arc_tools.unpack(a.entries[idx])
            assert decode_xet(raw).size == expected
            assert len(raw) == a.entries[idx].raw_size
    report["validated_archives"] = 30
    report["changed_entries"] = [2, 4]
    report["preview"] = str(OUT / "result_donor_v2_contact_sheet.png")
    (OUT / "VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "changed_archives": 30, "validated_archives": 30}))


if __name__ == "__main__":
    main()
