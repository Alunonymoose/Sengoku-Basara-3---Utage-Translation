#!/usr/bin/env python3
"""
xet_ps3.py -- Sengoku BASARA 3 Utage PS3 \\0XET read/write, RUNTIME-PROVEN contract (2026-09-25).

THE CONTRACT (supersedes the 2026-09-23 "PS3 big-endian RGB565 endpoint" rule)
  * BC colour endpoints are standard DXT little-endian RGB565 words. There is NO PS3 byte swap.
    (Header fields are still big-endian; only the BC colour endpoints were wrong.)
  * 0x2A = BC3/DXT5 storage + the Kuriimu2 PS3 YCbCr colour shader:
        stored RGBA = (Cr, alpha, Cb, Y), chroma neutral at 123
        display:  alpha=G, Y=A, Cb=B-123, Cr=R-123,
                  R=Y+1.402Cr, G=Y-0.344136Cb-0.714136Cr, B=Y+1.772Cb
        write:    Y=.299R+.587G+.114B, Cb=123-.168736R-.331264G+.5B, Cr=123+.5R-.418688G-.081312B
  * 0x17/0x18 = BC3 plain RGBA; 0x19 = BC1 plain; 0x15 = BC2 (read only); 0x27 = A8R8G8B8 (read only).

EVIDENCE (see README.md in this folder)
  * versus/menu.arc member 58 (kessen_001_ID_HQ): a BE-path write of stored (123,0,123,0) rendered in
    RPCS3 as an opaque navy box (8,63,140); this contract predicts (0,56,132) alpha 239. The LE+YCbCr
    re-encode renders correctly in-game (cold boot 2026-09-25).
  * Pristine JPN 0x2A sheets decoded with LE endpoints have chroma exactly at 123 (YCbCr signature);
    the runtime-verified 2026-09-18 title_004 (blue "Sengoku") only decodes correctly as LE+YCbCr.
  * Block-seam smoothness on 250+ real textures prefers LE for 0x2A (214/225), 0x17 (87/98), 0x19 (20/25).

WRITE RULES
  BC3 formats only (0x2A/0x17/0x18), mip 0, swizzle 0. Only 4x4 blocks that change are re-encoded;
  every untouched block, the header and other mips stay byte-identical. Candidate art is DISPLAY RGBA.

Bundles unchanged copies of xetenc.py + xet3.py (2026-09-24 recovery). Their BC3 block encoder is reused through an
endpoint byte-swap bridge. Do NOT call xetenc/xet3 directly for production any more: on their own they read and
write the endpoints in the wrong (big-endian) order.
"""
from __future__ import annotations
import os, struct, sys
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, '..', 'xetenc_RECOVERED_2026-09-24'), _HERE):  # bundled copies (same folder) win
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

MAGIC = b'\x00XET'
BC3 = {0x2A, 0x17, 0x18}
YCBCR = {0x2A}

def info(raw: bytes) -> dict:
    if raw[:4] != MAGIC:
        raise ValueError('not an XET resource')
    tf = struct.unpack_from('>I', raw, 8)[0]
    mips, w, h = tf & 0x3F, (tf >> 6) & 0x1FFF, (tf >> 19) & 0x1FFF
    offs = list(struct.unpack_from('>%dI' % mips, raw, 16))
    return {'width': w, 'height': h, 'mips': mips, 'format': raw[0x0E], 'mip_offsets': offs}

def _block_geom(raw):
    i = info(raw); f = i['format']
    bs = 8 if f == 0x19 else 16
    ep = 0 if bs == 8 else 8
    n = ((i['width'] + 3) // 4) * ((i['height'] + 3) // 4)
    return i, bs, ep, n

def swap_endpoints(raw: bytes) -> bytes:
    """Byte-swap the two RGB565 endpoint words of every mip-0 block (bridge to the BE-view tools)."""
    i, bs, ep, n = _block_geom(raw)
    if i['format'] not in (0x2A, 0x17, 0x18, 0x19, 0x15):
        raise ValueError('not a BC format: 0x%02X' % i['format'])
    b = bytearray(raw); off = i['mip_offsets'][0]
    for k in range(n):
        p = off + k * bs + ep
        b[p], b[p + 1] = b[p + 1], b[p]
        b[p + 2], b[p + 3] = b[p + 3], b[p + 2]
    return bytes(b)

# ---------------- fast vectorised decode (little-endian endpoints) ----------------
def _565(v):
    r = ((v >> 11) & 31).astype(np.int32); g = ((v >> 5) & 63).astype(np.int32); b = (v & 31).astype(np.int32)
    return np.stack([(r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31], -1)

def _colour(b8, four_always):
    c0 = b8[:, 0].astype(np.uint32) | (b8[:, 1].astype(np.uint32) << 8)
    c1 = b8[:, 2].astype(np.uint32) | (b8[:, 3].astype(np.uint32) << 8)
    e0, e1 = _565(c0), _565(c1)
    four = np.ones(len(c0), bool) if four_always else (c0 > c1)
    p2 = np.where(four[:, None], (2 * e0 + e1) // 3, (e0 + e1) // 2)
    p3 = np.where(four[:, None], (e0 + 2 * e1) // 3, 0)
    pal = np.stack([e0, e1, p2, p3], 1)
    idx = b8[:, 4].astype(np.uint32) | (b8[:, 5].astype(np.uint32) << 8) | (b8[:, 6].astype(np.uint32) << 16) | (b8[:, 7].astype(np.uint32) << 24)
    sel = np.stack([(idx >> (2 * t)) & 3 for t in range(16)], 1).astype(np.int64)
    rgb = np.take_along_axis(pal, sel[..., None].repeat(3, -1), 1)
    return rgb, (~four)[:, None] & (sel == 3)

def decode_storage(raw: bytes) -> np.ndarray:
    """Mip 0 stored channels (H,W,4 uint8) with the correct LE endpoint order. For 0x2A this is (Cr,alpha,Cb,Y)."""
    i = info(raw); f = i['format']; w, h = i['width'], i['height']; off = i['mip_offsets'][0]
    if f == 0x27:
        a = np.frombuffer(raw, np.uint8, count=w * h * 4, offset=off).reshape(h, w, 4)
        return a[..., [1, 2, 3, 0]].copy()
    _, bs, ep, n = _block_geom(raw)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    blk = np.frombuffer(raw, np.uint8, count=n * bs, offset=off).reshape(n, bs)
    if bs == 8:
        rgb, tr = _colour(blk, False); a = np.where(tr, 0, 255)
    else:
        rgb, _ = _colour(blk[:, 8:], True)
        if f == 0x15:
            a = np.stack([(blk[:, t // 2] >> (4 * (t % 2))) & 15 for t in range(16)], 1).astype(np.int32) * 17
        else:
            a0 = blk[:, 0].astype(np.int32); a1 = blk[:, 1].astype(np.int32)
            bits = np.zeros(n, np.uint64)
            for k in range(6):
                bits |= blk[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
            sel = np.stack([(bits >> np.uint64(3 * t)) & np.uint64(7) for t in range(16)], 1).astype(np.int64)
            p8 = np.where((a0 > a1)[:, None],
                          np.stack([a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)], 1),
                          np.stack([a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [np.zeros_like(a0), np.full_like(a0, 255)], 1))
            a = np.take_along_axis(p8, sel, 1)
    px = np.concatenate([rgb, a[..., None]], -1).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return px[:h, :w].astype(np.uint8)

def storage_to_display(st: np.ndarray, fmt: int) -> np.ndarray:
    if fmt not in YCBCR:
        return st.copy()
    s = st.astype(np.float64); a = s[..., 1]; Y = s[..., 3]; Cb = s[..., 2] - 123; Cr = s[..., 0] - 123
    out = np.stack([Y + 1.402 * Cr, Y - 0.344136 * Cb - 0.714136 * Cr, Y + 1.772 * Cb, a], -1)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)

def display_to_storage(rgba: np.ndarray, fmt: int) -> np.ndarray:
    if fmt not in YCBCR:
        return rgba.astype(np.uint8).copy()
    c = rgba.astype(np.float64); R, G, B, A = c[..., 0], c[..., 1], c[..., 2], c[..., 3]
    Y = 0.299 * R + 0.587 * G + 0.114 * B
    Cb = 123 - 0.168736 * R - 0.331264 * G + 0.5 * B
    Cr = 123 + 0.5 * R - 0.418688 * G - 0.081312 * B
    return np.clip(np.rint(np.stack([Cr, A, Cb, Y], -1)), 0, 255).astype(np.uint8)

def decode_display(raw: bytes) -> np.ndarray:
    """What the game shows (RGBA) for mip 0."""
    return storage_to_display(decode_storage(raw), info(raw)['format'])

# ---------------- write ----------------
def patch_display(raw: bytes, display_rgba: np.ndarray, mask: np.ndarray):
    """Replace the pixels selected by `mask` (H,W bool) with `display_rgba` (H,W,4, what the game should show).
    Returns (new_raw, blocks_touched, blocks_total). Untouched blocks stay byte-identical."""
    import xet3, xetenc  # BE-view encoder, used through the swap bridge
    i = info(raw); f = i['format']
    if f not in BC3:
        raise ValueError('write supported only for BC3 formats 0x2A/0x17/0x18, got 0x%02X' % f)
    if i['mips'] != 1:
        raise ValueError('multi-mip write is fail-closed (mips=%d)' % i['mips'])
    h, w = i['height'], i['width']
    if display_rgba.shape[:2] != (h, w) or mask.shape != (h, w):
        raise ValueError('candidate/mask must be %dx%d' % (w, h))
    sw = swap_endpoints(raw)
    base = np.array(xet3.decode(sw, 0), np.uint8).copy()   # exact stored channels in the encoder's own rounding
    new = base.copy()
    new[mask] = display_to_storage(display_rgba, f)[mask]
    out_sw, touched, total = xetenc.patch_xet(sw, 0, new)
    return swap_endpoints(out_sw), touched, total

def selftest(menu_arc_path: str, approved_png: str = None, installed_arc: str = None):
    """Regression: decode JPN/ENG menu.arc member 58 and (optionally) reproduce the installed v3 bytes."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import safe_arc  # canonical ARC tool (pin 7beb24a5...) must be importable
    e = safe_arc.parse_arc(open(menu_arc_path, 'rb').read())[58]
    st = decode_storage(e['raw'])
    m = st[..., 1] > 32
    print('member 58 chroma dev |R-123|,|B-123| medians:', int(np.median(np.abs(st[m, 0].astype(int) - 123))), int(np.median(np.abs(st[m, 2].astype(int) - 123))))
    if approved_png and installed_arc:
        from PIL import Image
        cand = np.array(Image.open(approved_png).convert('RGBA'))
        mask = np.zeros(st.shape[:2], bool)
        for x0, y0, x1, y1 in [(0,0,512,64),(0,64,512,128),(0,128,256,192),(256,128,512,192),(0,192,256,256),(256,192,512,256),(0,256,256,320),(256,256,512,320)]:
            mask[y0:y1, x0:x1] = True
        new, t, n = patch_display(e['raw'], cand, mask)
        live = safe_arc.parse_arc(open(installed_arc, 'rb').read())[58]['raw']
        print('reproduces installed member 58 byte-for-byte:', new == live, '(blocks touched %d/%d)' % (t, n))

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        selftest(*sys.argv[1:4])
    else:
        print(__doc__)
