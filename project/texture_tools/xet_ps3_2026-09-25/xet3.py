#!/usr/bin/env python3
"""
xet3.py -- MT Framework \0XET texture decoder (PS3, big-endian).

RECOVERED / RE-IMPLEMENTED 2026-09-24 from the fully-documented, proven
contract in this project's claude/2026-09-23-XET-BC3-FORMAT-SOLVED-decoder-
contract.md (validated 2026-09-23 on all 2516 TEX members across 66 ARCs,
0 errors). The original agent-local /home/claude/work/xet3.py from that
session was never durably preserved (confirmed missing from both E: and
Drive as of 2026-09-24 -- see BASARA Foundry's "00 READ FIRST - XET SOLVED
TOOL RECOVERY STATUS - 2026-09-23", P0 durability gap). This is a clean-
room re-implementation from the written spec, not a recovered original.

Header (big-endian; magic stored as b'\\0XET'):
  +0x00 u32   magic
  +0x04 u32   version/flags
  +0x08 u32   texFlags: mipCount = v & 0x3F
                        width    = (v >> 6)  & 0x1FFF
                        height   = (v >> 19) & 0x1FFF
  +0x0C u32   flags; byte at +0x0E is the pixel format id
  +0x10 u32[mipCount]  offset of each mip surface (absolute file offset)

Pixel formats:
  0x2A / 0x17 / 0x15  BC3/DXT5   1.0 bpp
  0x19                BC1/DXT1   0.5 bpp
  0x27                A8R8G8B8   4.0 bpp  (channel order in file: A,R,G,B)

BC3 block byte layout (PS3 quirk -- only u16-TYPED fields are byte-swapped;
byte ARRAYS are left as plain little-endian packings):
  bytes 0,1    alpha0, alpha1            plain bytes
  bytes 2..7   alpha 3-bit indices       byte array, LE 48-bit int, texel t at bits 3t
  bytes 8,9    colour0 RGB565            BIG-ENDIAN u16
  bytes 10,11  colour1 RGB565            BIG-ENDIAN u16
  bytes 12..15 colour 2-bit indices      byte array, LE u32, texel t at bits 2t
"""
import struct
import numpy as np

MAGIC = b'\x00XET'


def xet_info(raw: bytes) -> dict:
    if raw[0:4] != MAGIC:
        raise ValueError("not a \\0XET file (bad magic %r)" % raw[0:4])
    version = struct.unpack_from('>I', raw, 0x04)[0]
    tex_flags = struct.unpack_from('>I', raw, 0x08)[0]
    mip_count = tex_flags & 0x3F
    width = (tex_flags >> 6) & 0x1FFF
    height = (tex_flags >> 19) & 0x1FFF
    flags = struct.unpack_from('>I', raw, 0x0C)[0]
    pixel_format = (flags >> 8) & 0xFF  # byte at +0x0E
    return {
        'version': version,
        'mip_count': mip_count,
        'width': width,
        'height': height,
        'pixel_format': pixel_format,
        'header_bytes_at_0e': raw[0x0E],
    }


def mip_offsets(raw: bytes) -> list:
    info = xet_info(raw)
    n = info['mip_count']
    offs = list(struct.unpack_from('>%dI' % n, raw, 0x10))
    return offs


def mip_dims(width, height, level):
    w = max(1, width >> level)
    h = max(1, height >> level)
    return w, h


def bytes_per_pixel(pixel_format):
    if pixel_format in (0x2A, 0x17, 0x15):
        return 1.0   # BC3
    if pixel_format == 0x19:
        return 0.5   # BC1
    if pixel_format == 0x27:
        return 4.0   # A8R8G8B8
    raise ValueError("unknown pixel format 0x%02X" % pixel_format)


def mip_data_size(width, height, pixel_format):
    w, h = width, height
    bpp = bytes_per_pixel(pixel_format)
    if bpp in (1.0, 0.5):
        # block-compressed: ceil(w/4)*ceil(h/4) blocks * (16 or 8) bytes
        bw, bh = (w + 3) // 4, (h + 3) // 4
        block_bytes = 16 if bpp == 1.0 else 8
        return bw * bh * block_bytes
    return int(w * h * bpp)


# ---------------------------------------------------------------- BC1/BC3 --

def _rgb565_to_rgb8(c):
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    r8 = (r << 3) | (r >> 2)
    g8 = (g << 2) | (g >> 4)
    b8 = (b << 3) | (b >> 2)
    return r8, g8, b8


def _color_palette(c0, c1):
    r0, g0, b0 = _rgb565_to_rgb8(c0)
    r1, g1, b1 = _rgb565_to_rgb8(c1)
    # BC3's colour block is ALWAYS the 4-colour (no punch-through) mode,
    # regardless of whether c0 > c1 numerically.
    c2 = ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3)
    c3 = ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3)
    return [(r0, g0, b0), (r1, g1, b1), c2, c3]


def _alpha_palette(a0, a1):
    if a0 > a1:
        return [
            a0, a1,
            (6 * a0 + 1 * a1) // 7,
            (5 * a0 + 2 * a1) // 7,
            (4 * a0 + 3 * a1) // 7,
            (3 * a0 + 4 * a1) // 7,
            (2 * a0 + 5 * a1) // 7,
            (1 * a0 + 6 * a1) // 7,
        ]
    else:
        return [
            a0, a1,
            (4 * a0 + 1 * a1) // 5,
            (3 * a0 + 2 * a1) // 5,
            (2 * a0 + 3 * a1) // 5,
            (1 * a0 + 4 * a1) // 5,
            0, 255,
        ]


def decode_block_bc3(block16: bytes):
    """Return a 4x4x4 uint8 RGBA numpy array for one 16-byte BC3 block."""
    a0, a1 = block16[0], block16[1]
    apal = _alpha_palette(a0, a1)
    aidx_bits = int.from_bytes(block16[2:8], 'little')
    alphas = [apal[(aidx_bits >> (3 * t)) & 0x7] for t in range(16)]

    c0 = struct.unpack_from('>H', block16, 8)[0]
    c1 = struct.unpack_from('>H', block16, 10)[0]
    cpal = _color_palette(c0, c1)
    cidx_bits = struct.unpack_from('<I', block16, 12)[0]
    colors = [cpal[(cidx_bits >> (2 * t)) & 0x3] for t in range(16)]

    out = np.zeros((4, 4, 4), dtype=np.uint8)
    for t in range(16):
        y, x = divmod(t, 4)
        r, g, b = colors[t]
        out[y, x] = (r, g, b, alphas[t])
    return out


def decode_block_bc1(block8: bytes):
    c0 = struct.unpack_from('>H', block8, 0)[0]
    c1 = struct.unpack_from('>H', block8, 2)[0]
    cpal = _color_palette(c0, c1)
    cidx_bits = struct.unpack_from('<I', block8, 4)[0]
    out = np.zeros((4, 4, 4), dtype=np.uint8)
    for t in range(16):
        y, x = divmod(t, 4)
        r, g, b = cpal[(cidx_bits >> (2 * t)) & 0x3]
        out[y, x] = (r, g, b, 255)
    return out


def decode(raw: bytes, level: int = 0) -> np.ndarray:
    info = xet_info(raw)
    offs = mip_offsets(raw)
    if level >= info['mip_count']:
        raise ValueError("level %d >= mip_count %d" % (level, info['mip_count']))
    w, h = mip_dims(info['width'], info['height'], level)
    pf = info['pixel_format']
    start = offs[level]

    if pf == 0x27:
        # A,R,G,B in file -> RGBA out
        n = w * h
        arb = np.frombuffer(raw, dtype=np.uint8, count=n * 4, offset=start)
        arb = arb.reshape(h, w, 4)
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[..., 0] = arb[..., 1]  # R
        out[..., 1] = arb[..., 2]  # G
        out[..., 2] = arb[..., 3]  # B
        out[..., 3] = arb[..., 0]  # A
        return out

    bw, bh = (w + 3) // 4, (h + 3) // 4
    out = np.zeros((bh * 4, bw * 4, 4), dtype=np.uint8)
    if pf in (0x2A, 0x17, 0x15):
        blk_bytes = 16
        decode_block = decode_block_bc3
    elif pf == 0x19:
        blk_bytes = 8
        decode_block = decode_block_bc1
    else:
        raise ValueError("unsupported pixel format 0x%02X" % pf)

    for by in range(bh):
        for bx in range(bw):
            idx = by * bw + bx
            off = start + idx * blk_bytes
            block = raw[off:off + blk_bytes]
            out[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4] = decode_block(block)

    return out[:h, :w]


if __name__ == '__main__':
    import sys
    from PIL import Image
    path = sys.argv[1]
    raw = open(path, 'rb').read()
    info = xet_info(raw)
    print(path, info, 'mip_offsets=', mip_offsets(raw), 'file_len=', len(raw))
    img = decode(raw, 0)
    out_path = path.rsplit('.', 1)[0] + '_decoded.png'
    Image.fromarray(img, 'RGBA').save(out_path)
    print('wrote', out_path)
