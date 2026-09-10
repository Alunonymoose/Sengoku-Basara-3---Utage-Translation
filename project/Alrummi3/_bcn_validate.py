"""Round-trip real game textures through the encoder and measure the damage.

A texture in the game is already block-compressed, so decoding it and encoding
it again should land almost exactly back where it started - a good encoder
rediscovers nearly the same endpoints.  Large error here means the encoder is
wrong, not that the test is unfair.
"""
import io, struct, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import alrummi3_core as c
import bcn
import donor_index as d
from character_map import local_index_path


def dds_header(w, h, size, fourcc):
    pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc.encode(), 0, 0, 0, 0, 0)
    return (b"DDS " + struct.pack("<IIIIIII", 124, 0x000A1007, h, w, size, 0, 1)
            + b"\0" * 44 + pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0))


def decode_blocks(blob, w, h, fourcc):
    block = 8 if fourcc == "DXT1" else 16
    size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    with Image.open(io.BytesIO(dds_header(w, h, size, fourcc) + blob[:size])) as im:
        out = im.convert("RGBA")
        out.load()
    return out


def measure(a: Image.Image, b: Image.Image):
    x = np.asarray(a.convert("RGBA"), dtype=np.int16)
    y = np.asarray(b.convert("RGBA"), dtype=np.int16)
    diff = np.abs(x - y)
    rgb = diff[..., :3]
    alpha = diff[..., 3]
    # RGB under a fully transparent pixel is never drawn, so counting it
    # measures noise rather than quality.  Score only what is visible.
    visible = (x[..., 3] >= 8) | (y[..., 3] >= 8)
    if visible.any():
        vis_rgb = rgb[visible]
        mse = float((vis_rgb.astype(np.float64) ** 2).mean())
    else:
        vis_rgb = rgb.reshape(-1, 3)
        mse = float((vis_rgb.astype(np.float64) ** 2).mean())
    psnr = float("inf") if mse == 0 else 10 * np.log10(255.0 * 255.0 / mse)
    rgb = vis_rgb
    return {
        "rgb_mean": float(rgb.mean()),
        "rgb_max": int(rgb.max()),
        "alpha_mean": float(alpha.mean()),
        "alpha_max": int(alpha.max()),
        "psnr": psnr,
    }


index = d.load_donor_index(local_index_path(HERE)) or d.load_donor_index(d.donor_index_path(HERE))
archives = index["archives"]

samples = {"DXT5": [], "DXT1": []}
for path in archives[::13]:
    if len(samples["DXT5"]) >= 12 and len(samples["DXT1"]) >= 12:
        break
    try:
        arc = c.parse_arc(Path(path))
    except Exception:
        continue
    for e in arc.entries:
        try:
            raw = c.unpack_entry(e)
        except Exception:
            continue
        if raw[:4] != b"\0XET":
            continue
        try:
            info = c.xet_info(raw)
        except Exception:
            continue
        if info.width * info.height > 512 * 512:
            continue
        bucket = samples.get(info.fourcc)
        if bucket is None or len(bucket) >= 12:
            continue
        bucket.append((e.name, raw, info))

for fourcc in ("DXT5", "DXT1"):
    rows = samples[fourcc]
    print(f"\n=== {fourcc}: {len(rows)} real textures ===")
    if not rows:
        continue
    totals = []
    elapsed = 0.0
    pixels = 0
    for name, raw, info in rows:
        original = c.decode_xet(raw)[0]
        arr = np.asarray(original.convert("RGBA"), dtype=np.uint8)
        t = time.perf_counter()
        blob = bcn.encode(arr, fourcc)
        elapsed += time.perf_counter() - t
        pixels += info.width * info.height
        again = decode_blocks(blob, info.width, info.height, fourcc)
        m = measure(original, again)
        totals.append(m)
        print(f"  {info.width:4d}x{info.height:<4d} rgb mean {m['rgb_mean']:5.2f} max {m['rgb_max']:3d} "
              f"| alpha mean {m['alpha_mean']:5.2f} max {m['alpha_max']:3d} "
              f"| PSNR {m['psnr']:5.1f} dB  {name.split(chr(92))[-1][:28]}")
    print(f"  ---- mean PSNR {np.mean([t['psnr'] for t in totals]):.1f} dB, "
          f"rgb mean err {np.mean([t['rgb_mean'] for t in totals]):.2f}, "
          f"alpha mean err {np.mean([t['alpha_mean'] for t in totals]):.2f}")
    print(f"  ---- {pixels/1e6:.2f} Mpx in {elapsed:.2f}s = {pixels/max(elapsed,1e-6)/1e6:.1f} Mpx/s")

# --- head to head against the old encoder, on DXT5 ----------------------
print("\n=== new encoder vs the old one (same DXT5 textures) ===")
for name, raw, info in samples["DXT5"][:6]:
    original = c.decode_xet(raw)[0]
    arr = np.asarray(original.convert("RGBA"), dtype=np.uint8)
    new_blob = bcn.encode(arr, "DXT5")
    new_img = decode_blocks(new_blob, info.width, info.height, "DXT5")
    old_raw = c.patch_bc3_rect(raw, original, c.Region(0, 0, info.width, info.height))
    old_img = c.decode_xet(old_raw)[0]
    n, o = measure(original, new_img), measure(original, old_img)
    print(f"  {info.width:4d}x{info.height:<4d} PSNR  new {n['psnr']:5.1f} dB   old {o['psnr']:5.1f} dB"
          f"   ({n['psnr'] - o['psnr']:+.1f})   {name.split(chr(92))[-1][:26]}")
