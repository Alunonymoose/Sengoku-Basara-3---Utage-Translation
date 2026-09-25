#!/usr/bin/env python3
"""utage_xet -- canonical Python XET codec for Sengoku BASARA 3 Utage (PS3).

This is the ONE Python module that reads and writes Utage XET textures.
Review tools, the release audit, donor matching and texture jobs must import
it instead of carrying private decoders/encoders.

CONTRACT (2026-09-25, runtime-backed; supersedes the 2026-09-23 "PS3 endian"
wording everywhere):

* XET container fields (magic, bitfields, mip offset table) are big-endian.
* The BC1/BC2/BC3 block payload is STANDARD DXT byte order: RGB565 colour
  endpoints are little-endian u16 exactly as on PC. There is NO PS3 endpoint
  byte swap. Evidence: title_004 0x2A runtime-verified 2026-09-18 with
  standard order; the 2026-09-24 title_004 runtime failure of the swapped
  path (green rectangle / magenta logo); the 2026-09-25 menu.arc member 58
  runtime screenshot whose navy plate (8,63,140) matched the predicted
  (0,56,132) of the swapped+plain writer, while standard order decodes the
  JPN original with chroma exactly on the 123 neutral point.
* Format 0x2A (and 0x2B for reading) stores the Kuriimu2 MT Framework PS3
  YCbCr shader representation inside BC3: stored RGBA = (Cr, alpha, Cb, Y)
  with neutral chroma 123. Artist-facing pixels are DISPLAY RGBA; the codec
  converts display <-> stored. Never BC3-encode display RGBA into 0x2A.
* 0x15 is DXT3/BC2 (read only). 0x19/0x13/0x14 are BC1 (read only).
  0x27 is A8R8G8B8 (read only). 0x2B write is blocked (RBxG/base+mask).
* Writes: single-mip, swizzle 0, exact-length resources only, block-graft
  onto the CURRENT LIVE TARGET (untouched 16-byte blocks copied verbatim).

Evidence words: this module is SOFTWARE/FIXTURE verified by tests/. A newly
written game texture still needs final-ARC re-extract + RPCS3 cold boot.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, asdict, field
from typing import Optional

import numpy as np

__version__ = "1.0.0"

MAGIC = b"\x00XET"
NEUTRAL_CHROMA = 123

# code -> (codec, semantics, read, write)
FORMATS: dict[int, tuple[str, str, bool, bool]] = {
    0x13: ("BC1", "display", True, False),
    0x14: ("BC1", "display", True, False),
    0x15: ("BC2", "display", True, False),
    0x17: ("BC3", "display", True, True),
    0x18: ("BC3", "display", True, True),
    0x19: ("BC1", "display", True, False),
    0x27: ("ARGB8", "display", True, False),
    0x2A: ("BC3", "ycbcr", True, True),
    0x2B: ("BC3", "ycbcr_rbxg", True, False),
}


class XetError(ValueError):
    """Raised for malformed resources and every fail-closed refusal."""


# --------------------------------------------------------------------------
# header
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class XetInfo:
    version: int
    swizzle: int
    alpha_flags: int
    mip_count: int
    width: int
    height: int
    format_code: int
    mip_offsets: tuple[int, ...]
    length: int

    @property
    def codec(self) -> str:
        return FORMATS[self.format_code][0] if self.format_code in FORMATS else "UNKNOWN"

    @property
    def semantics(self) -> str:
        return FORMATS[self.format_code][1] if self.format_code in FORMATS else "unknown"


def xet_info(raw: bytes) -> XetInfo:
    raw = bytes(raw)
    if len(raw) < 20 or raw[:4] != MAGIC:
        raise XetError("not a PS3 XET resource")
    b4, b8, _b12 = struct.unpack_from(">III", raw, 4)
    mip = b8 & 0x3F
    width = (b8 >> 6) & 0x1FFF
    height = (b8 >> 19) & 0x1FFF
    if mip < 1 or width < 1 or height < 1:
        raise XetError(f"invalid dimensions/mips {width}x{height} mip={mip}")
    table_end = 16 + 4 * mip
    if table_end > len(raw):
        raise XetError("mip offset table exceeds resource")
    offs = struct.unpack_from(f">{mip}I", raw, 16)
    if any(o < table_end or o >= len(raw) for o in offs) or tuple(sorted(offs)) != offs:
        raise XetError(f"invalid mip offsets {offs}")
    return XetInfo(
        version=b4 & 0xFFF, swizzle=(b4 >> 12) & 0xFFF, alpha_flags=(b4 >> 28) & 0xF,
        mip_count=mip, width=width, height=height, format_code=raw[0x0E],
        mip_offsets=tuple(offs), length=len(raw),
    )


def level_dims(info: XetInfo, level: int) -> tuple[int, int]:
    return max(1, info.width >> level), max(1, info.height >> level)


def surface_bytes(codec: str, w: int, h: int) -> int:
    blocks = ((w + 3) // 4) * ((h + 3) // 4)
    if codec in ("BC2", "BC3"):
        return blocks * 16
    if codec == "BC1":
        return blocks * 8
    if codec == "ARGB8":
        return w * h * 4
    raise XetError(f"unsupported codec {codec}")


def _require_read(info: XetInfo, level: int) -> None:
    if info.format_code not in FORMATS:
        raise XetError(f"unknown XET format 0x{info.format_code:02X}; refusing to guess")
    if info.swizzle != 0:
        raise XetError(f"XET declares swizzle {info.swizzle}; no certified de-swizzle path")
    if not 0 <= level < info.mip_count:
        raise XetError(f"bad mip level {level}")
    w, h = level_dims(info, level)
    end = info.mip_offsets[level] + surface_bytes(info.codec, w, h)
    if end > info.length:
        raise XetError(f"mip {level} payload exceeds resource")


# --------------------------------------------------------------------------
# block decode (standard DXT byte order, vectorised)
# --------------------------------------------------------------------------
def _expand565(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.int32)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1)


def _colour_blocks(cb: np.ndarray, four_colour_only: bool) -> tuple[np.ndarray, np.ndarray]:
    """cb: (N,8) uint8 BC1-style colour block -> (N,16,3) rgb, (N,16) alpha."""
    c0 = cb[:, 0].astype(np.int32) | (cb[:, 1].astype(np.int32) << 8)
    c1 = cb[:, 2].astype(np.int32) | (cb[:, 3].astype(np.int32) << 8)
    e0, e1 = _expand565(c0), _expand565(c1)
    four = np.ones(len(cb), bool) if four_colour_only else (c0 > c1)
    p2 = np.where(four[:, None], (2 * e0 + e1) // 3, (e0 + e1) // 2)
    p3 = np.where(four[:, None], (e0 + 2 * e1) // 3, 0)
    pal = np.stack([e0, e1, p2, p3], 1)  # N,4,3
    bits = cb[:, 4:8].copy().view("<u4").reshape(-1).astype(np.int64)
    idx = (bits[:, None] >> (2 * np.arange(16))) & 3
    rgb = np.take_along_axis(pal, idx[:, :, None].repeat(3, 2), 1)
    alpha = np.where((~four[:, None]) & (idx == 3), 0, 255)
    return rgb, alpha


def _alpha_pal(a0: np.ndarray, a1: np.ndarray) -> np.ndarray:
    a0 = a0.astype(np.int32)
    a1 = a1.astype(np.int32)
    eight = np.stack([a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)], 1)
    six = np.stack([a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)]
                   + [np.zeros_like(a0), np.full_like(a0, 255)], 1)
    return np.where((a0 > a1)[:, None], eight, six)


def _decode_blocks(codec: str, payload: bytes, nblocks: int) -> np.ndarray:
    """-> (N,16,4) uint8 storage RGBA in texel order t = y*4+x."""
    if codec == "BC1":
        blk = np.frombuffer(payload, np.uint8, nblocks * 8).reshape(nblocks, 8)
        rgb, a = _colour_blocks(blk, False)
    else:
        blk = np.frombuffer(payload, np.uint8, nblocks * 16).reshape(nblocks, 16)
        rgb, _ = _colour_blocks(blk[:, 8:16], True)
        if codec == "BC2":
            bits = blk[:, 0:8].copy().view("<u8").reshape(-1)
            a = ((bits[:, None] >> (4 * np.arange(16, dtype=np.uint64))) & 0xF).astype(np.int32) * 17
        else:
            pal = _alpha_pal(blk[:, 0], blk[:, 1])
            bits = np.zeros(nblocks, np.int64)
            for i in range(6):
                bits |= blk[:, 2 + i].astype(np.int64) << (8 * i)
            idx = (bits[:, None] >> (3 * np.arange(16))) & 7
            a = np.take_along_axis(pal, idx, 1)
    return np.concatenate([rgb, a[:, :, None]], 2).astype(np.uint8)


def _blocks_to_image(blocks: np.ndarray, w: int, h: int) -> np.ndarray:
    bw, bh = (w + 3) // 4, (h + 3) // 4
    img = blocks.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return np.ascontiguousarray(img[:h, :w])


def decode_storage(raw: bytes, level: int = 0) -> np.ndarray:
    """Physical stored channels (H,W,4) uint8. NOT artist-facing for 0x2A/0x2B."""
    info = xet_info(raw)
    _require_read(info, level)
    w, h = level_dims(info, level)
    off = info.mip_offsets[level]
    if info.codec == "ARGB8":
        a = np.frombuffer(raw, np.uint8, w * h * 4, off).reshape(h, w, 4)
        return np.ascontiguousarray(a[..., [1, 2, 3, 0]])
    n = ((w + 3) // 4) * ((h + 3) // 4)
    payload = raw[off: off + surface_bytes(info.codec, w, h)]
    return _blocks_to_image(_decode_blocks(info.codec, payload, n), w, h)


# --------------------------------------------------------------------------
# 0x2A YCbCr shader (exact Kuriimu2 / Foundry C# arithmetic: truncate, clamp)
# --------------------------------------------------------------------------
def _clamp_trunc(x: np.ndarray) -> np.ndarray:
    return np.clip(np.trunc(x), 0, 255).astype(np.uint8)


def storage_to_display(storage: np.ndarray) -> np.ndarray:
    s = storage.astype(np.float64)
    y, cb, cr = s[..., 3], s[..., 2] - NEUTRAL_CHROMA, s[..., 0] - NEUTRAL_CHROMA
    out = np.empty(storage.shape, np.uint8)
    out[..., 0] = _clamp_trunc(y + 1.402 * cr)
    out[..., 1] = _clamp_trunc(y - 0.344136 * cb - 0.714136 * cr)
    out[..., 2] = _clamp_trunc(y + 1.772 * cb)
    out[..., 3] = storage[..., 1]
    return out


def display_to_storage(display: np.ndarray) -> np.ndarray:
    d = display.astype(np.float64)
    r, g, b = d[..., 0], d[..., 1], d[..., 2]
    out = np.empty(display.shape, np.uint8)
    out[..., 0] = _clamp_trunc(NEUTRAL_CHROMA + 0.5 * r - 0.418688 * g - 0.081312 * b)
    out[..., 1] = display[..., 3]
    out[..., 2] = _clamp_trunc(NEUTRAL_CHROMA - 0.168736 * r - 0.331264 * g + 0.5 * b)
    out[..., 3] = _clamp_trunc(0.299 * r + 0.587 * g + 0.114 * b)
    return out


def decode_display(raw: bytes, level: int = 0) -> np.ndarray:
    """Artist/game-visible RGBA (H,W,4). Use this for every preview/candidate."""
    info = xet_info(raw)
    st = decode_storage(raw, level)
    if info.semantics.startswith("ycbcr"):
        return storage_to_display(st)
    return st


# --------------------------------------------------------------------------
# BC3 block encoder (storage space). Deterministic; always emits c0 > c1 so
# the colour block is 4-colour on every decoder, including GPUs that honour
# the BC1 3-colour rule inside DXT5.
# --------------------------------------------------------------------------
def _q565(c: np.ndarray) -> int:
    c = np.clip(np.rint(c), 0, 255).astype(int)
    return ((c[0] * 31 + 127) // 255) << 11 | ((c[1] * 63 + 127) // 255) << 5 | ((c[2] * 31 + 127) // 255)


def _pal4(q0: int, q1: int) -> np.ndarray:
    e = _expand565(np.array([q0, q1]))
    return np.stack([e[0], e[1], (2 * e[0] + e[1]) // 3, (e[0] + 2 * e[1]) // 3])


def _fit_colour(px: np.ndarray, weight: np.ndarray) -> tuple[int, int, np.ndarray]:
    """px (16,3) float, weight (16,) -> (c0, c1, idx[16]) minimising weighted SSE."""
    cands: list[tuple[int, int]] = []
    lo, hi = px.min(0), px.max(0)
    cands.append((_q565(hi), _q565(lo)))
    mean = (px * weight[:, None]).sum(0) / max(weight.sum(), 1e-9)
    cen = px - mean
    cov = (cen * weight[:, None]).T @ cen
    if np.any(cov):
        axis = np.linalg.eigh(cov)[1][:, -1]
        proj = cen @ axis
        cands.append((_q565(mean + axis * proj.max()), _q565(mean + axis * proj.min())))
    best = None
    for q0, q1 in cands:
        for _ in range(3):  # least-squares endpoint refinement
            pal = _pal4(*_order(q0, q1))
            idx = ((px[:, None, :] - pal[None]) ** 2).sum(2).argmin(1)
            err = float(((((px - pal[idx]) ** 2).sum(1)) * weight).sum())
            o0, o1 = _order(q0, q1)
            if best is None or err < best[0]:
                best = (err, o0, o1, idx)
            t = np.array([0, 1, 2 / 3, 1 / 3])[idx]  # weight of endpoint0
            wa, wb = t * weight, (1 - t) * weight
            A = np.array([[np.dot(wa, t), np.dot(wa, 1 - t)], [np.dot(wb, t), np.dot(wb, 1 - t)]])
            if abs(np.linalg.det(A)) < 1e-9:
                break
            B = np.stack([wa @ px, wb @ px])
            e0, e1 = np.linalg.solve(A, B)
            q0, q1 = _q565(e0), _q565(e1)
    _, c0, c1, idx = best
    pal = _pal4(c0, c1)
    idx = ((px[:, None, :] - pal[None]) ** 2).sum(2).argmin(1)
    return c0, c1, idx


def _order(q0: int, q1: int) -> tuple[int, int]:
    if q0 == q1:
        return (q0, q0 - 1) if q0 > 0 else (1, 0)
    return (q0, q1) if q0 > q1 else (q1, q0)


def _fit_alpha(a: np.ndarray) -> tuple[int, int, np.ndarray]:
    a = a.astype(np.int32)
    lo, hi = int(a.min()), int(a.max())
    opts = []
    if lo == hi:
        opts.append((hi, lo))
    else:
        opts.append((hi, lo))  # 8-value
        inner = a[(a > 0) & (a < 255)]
        if inner.size:
            opts.append((int(inner.min()), int(inner.max())))  # 6-value + 0/255
        else:
            opts.append((0, 255))
    best = None
    for a0, a1 in opts:
        pal = _alpha_pal(np.array([a0]), np.array([a1]))[0]
        idx = np.abs(a[:, None] - pal[None]).argmin(1)
        err = int(np.abs(a - pal[idx]).sum())
        if best is None or err < best[0]:
            best = (err, a0, a1, idx)
    return best[1], best[2], best[3]


def encode_bc3_block(storage_block: np.ndarray) -> bytes:
    """(4,4,4) or (16,4) storage RGBA -> 16-byte standard-order BC3 block."""
    px = storage_block.reshape(16, 4)
    a0, a1, aidx = _fit_alpha(px[:, 3])
    # colour error is weighted by visibility only for plain formats; for 0x2A
    # the "alpha" slot carries luminance Y, so every texel counts equally.
    c0, c1, cidx = _fit_colour(px[:, :3].astype(np.float64), np.ones(16))
    abits = 0
    for t in range(16):
        abits |= int(aidx[t]) << (3 * t)
    cbits = 0
    for t in range(16):
        cbits |= int(cidx[t]) << (2 * t)
    return bytes([a0, a1]) + abits.to_bytes(6, "little") + struct.pack("<HHI", c0, c1, cbits)


def encode_bc3_block_display(display_block: np.ndarray, weight_by_alpha: bool = True) -> bytes:
    """Plain 0x17/0x18 variant: colour error weighted by display alpha."""
    px = display_block.reshape(16, 4)
    a0, a1, aidx = _fit_alpha(px[:, 3])
    w = np.maximum(px[:, 3].astype(np.float64) / 255.0, 0.02) if weight_by_alpha else np.ones(16)
    c0, c1, cidx = _fit_colour(px[:, :3].astype(np.float64), w)
    abits = sum(int(aidx[t]) << (3 * t) for t in range(16))
    cbits = sum(int(cidx[t]) << (2 * t) for t in range(16))
    return bytes([a0, a1]) + abits.to_bytes(6, "little") + struct.pack("<HHI", c0, c1, cbits)


# --------------------------------------------------------------------------
# transparent-RGB conditioning
# --------------------------------------------------------------------------
def prefill_transparent_rgb(display: np.ndarray, mode: str = "dilate",
                            colour: Optional[tuple[int, int, int]] = None) -> np.ndarray:
    """Give alpha==0 texels a sensible hidden RGB so BC endpoints are not
    poisoned by black. 'none' | 'dilate' (nearest visible colour) | 'colour'."""
    out = display.copy()
    clear = out[..., 3] == 0
    if mode == "none" or not clear.any() or clear.all():
        return out
    if mode == "colour":
        if colour is None:
            raise XetError("prefill mode 'colour' needs colour=(r,g,b)")
        out[clear, :3] = colour
        return out
    if mode != "dilate":
        raise XetError(f"unknown prefill mode {mode}")
    rgb = out[..., :3].astype(np.int32)
    known = ~clear
    for _ in range(64):
        if known.all():
            break
        acc = np.zeros(rgb.shape, np.int64)
        cnt = np.zeros(known.shape, np.int64)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            k = np.roll(known, (dy, dx), (0, 1))
            v = np.roll(rgb, (dy, dx), (0, 1))
            acc += np.where(k[..., None], v, 0)
            cnt += k
        grow = (~known) & (cnt > 0)
        rgb[grow] = acc[grow] // cnt[grow][:, None]
        known = known | grow
    out[..., :3] = rgb.astype(np.uint8)
    return out


# --------------------------------------------------------------------------
# semantic preflight / byte-order evidence
# --------------------------------------------------------------------------
def byte_order_evidence(raw: bytes, level: int = 0) -> dict:
    """For YCbCr formats: how well each endpoint byte order explains the data.

    Real 0x2A art stores chroma clustered on 123 wherever it is neutral
    (white/black/grey lettering, outlines). Decoding with the wrong order
    scatters that chroma. The metric is the share of covered texels whose
    stored Cr and Cb both lie within +-12 of 123.
    """
    info = xet_info(raw)
    _require_read(info, level)
    if not info.semantics.startswith("ycbcr"):
        return {"applicable": False}
    w, h = level_dims(info, level)
    off = info.mip_offsets[level]
    size = surface_bytes("BC3", w, h)
    std = bytes(raw[off:off + size])
    sw = bytearray(std)
    for o in range(0, size, 16):
        sw[o + 8], sw[o + 9], sw[o + 10], sw[o + 11] = sw[o + 9], sw[o + 8], sw[o + 11], sw[o + 10]
    n = size // 16
    res = {"applicable": True}
    for name, payload in (("standard", std), ("swapped", bytes(sw))):
        st = _decode_blocks("BC3", payload, n).reshape(-1, 4).astype(int)
        covered = st[:, 1] > 16
        if not covered.any():
            res[name] = None
            continue
        near = (np.abs(st[covered, 0] - 123) <= 12) & (np.abs(st[covered, 2] - 123) <= 12)
        res[name] = round(float(near.mean()), 4)
    s, t = res.get("standard"), res.get("swapped")
    res["verdict"] = ("standard" if (s or 0) >= (t or 0) + 0.10 else
                      "swapped" if (t or 0) >= (s or 0) + 0.10 else "inconclusive")
    return res


# --------------------------------------------------------------------------
# block graft writer
# --------------------------------------------------------------------------
@dataclass
class GraftReport:
    tool: str
    format_code: str
    width: int
    height: int
    blocks_total: int
    blocks_touched: int
    touched_blocks: list = field(default_factory=list)
    prefill: str = "dilate"
    source_sha256: str = ""
    output_sha256: str = ""
    candidate_sha256: str = ""
    max_abs_error_in_touched: int = 0
    mean_abs_error_in_touched: float = 0.0
    outside_touched_bytes_identical: bool = False
    outside_touched_display_identical: bool = False
    byte_order_evidence: dict = field(default_factory=dict)
    ok: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def sha256(b: bytes) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def graft(target: bytes, candidate_display: np.ndarray, *, mask: Optional[np.ndarray] = None,
          prefill: str = "dilate", prefill_colour: Optional[tuple[int, int, int]] = None,
          allow_inconclusive_byte_order: bool = False) -> tuple[bytes, GraftReport]:
    """Write `candidate_display` (H,W,4 DISPLAY RGBA) into the current live
    `target` XET, re-encoding only 4x4 blocks that differ. Fail-closed."""
    target = bytes(target)
    info = xet_info(target)
    _require_read(info, 0)
    if not FORMATS[info.format_code][3]:
        raise XetError(f"write of format 0x{info.format_code:02X} ({info.codec}/{info.semantics}) is not certified")
    if info.mip_count != 1:
        raise XetError("multi-mip XET: refusing to leave stale lower mips; certified mip writer required")
    w, h = info.width, info.height
    off = info.mip_offsets[0]
    size = surface_bytes("BC3", w, h)
    if off + size != info.length:
        raise XetError("XET has trailing data after the top level; refusing")
    cand = np.asarray(candidate_display, np.uint8)
    if cand.shape != (h, w, 4):
        raise XetError(f"candidate shape {cand.shape} != {(h, w, 4)}")

    evidence = byte_order_evidence(target) if info.semantics.startswith("ycbcr") else {"applicable": False}
    if evidence.get("verdict") == "swapped":
        raise XetError("target decodes as endpoint-SWAPPED data (legacy writer output?). "
                       "Repair from a trusted source before grafting. " + json.dumps(evidence))
    if evidence.get("verdict") == "inconclusive" and not allow_inconclusive_byte_order:
        raise XetError("byte-order preflight inconclusive; inspect decode_display() visually and "
                       "re-run with allow_inconclusive_byte_order=True. " + json.dumps(evidence))

    current = decode_display(target)
    if mask is not None:
        mask = np.asarray(mask, bool)
        if mask.shape != (h, w):
            raise XetError("mask shape mismatch")
        if not np.array_equal(cand[~mask], current[~mask]):
            raise XetError("candidate differs from the live decode OUTSIDE the approved mask")

    bw, bh = (w + 3) // 4, (h + 3) // 4
    pad = lambda im: np.pad(im, ((0, bh * 4 - h), (0, bw * 4 - w), (0, 0)), mode="edge")
    cur_p, cand_p = pad(current), pad(cand)
    changed = (cur_p != cand_p).any(2).reshape(bh, 4, bw, 4).any((1, 3))
    touched = [(int(by), int(bx)) for by, bx in zip(*np.nonzero(changed))]

    enc_src = prefill_transparent_rgb(cand_p, prefill, prefill_colour)
    ycbcr = info.semantics.startswith("ycbcr")
    if ycbcr:
        enc_src = display_to_storage(enc_src)

    out = bytearray(target)
    for by, bx in touched:
        blk = enc_src[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4]
        o = off + (by * bw + bx) * 16
        out[o:o + 16] = encode_bc3_block(blk) if ycbcr else encode_bc3_block_display(blk)
    out = bytes(out)

    # independent verification
    touched_ranges = {off + (by * bw + bx) * 16 for by, bx in touched}
    bytes_ok = all(out[i:i + 16] == target[i:i + 16]
                   for i in range(off, off + size, 16) if i not in touched_ranges) \
        and out[:off] == target[:off]
    after = pad(decode_display(out))
    tmask = np.kron(changed, np.ones((4, 4), bool))
    disp_ok = np.array_equal(after[~tmask], cur_p[~tmask])
    vis = cand_p[..., 3] > 0
    diff = np.abs(after.astype(int) - cand_p.astype(int))
    diff[..., :3] *= vis[..., None]  # hidden RGB under alpha 0 is not an error
    tdiff = diff[tmask] if touched else np.zeros((0, 4), int)
    rep = GraftReport(
        tool=f"utage_xet {__version__}", format_code=f"0x{info.format_code:02X}", width=w, height=h,
        blocks_total=bw * bh, blocks_touched=len(touched), touched_blocks=touched, prefill=prefill,
        source_sha256=sha256(target), output_sha256=sha256(out), candidate_sha256=sha256(cand.tobytes()),
        max_abs_error_in_touched=int(tdiff.max()) if tdiff.size else 0,
        mean_abs_error_in_touched=round(float(tdiff.mean()), 3) if tdiff.size else 0.0,
        outside_touched_bytes_identical=bool(bytes_ok), outside_touched_display_identical=bool(disp_ok),
        byte_order_evidence=evidence,
    )
    rep.ok = rep.outside_touched_bytes_identical and rep.outside_touched_display_identical
    if not rep.ok:
        raise XetError("post-write verification failed: " + rep.to_json())
    return out, rep


# --------------------------------------------------------------------------
# ENG vs reference block scan (finds legacy/mis-encoded edits)
# --------------------------------------------------------------------------
def _legacy_view(payload: bytes, n: int) -> np.ndarray:
    """How the quarantined xetenc/xet3 pair saw a BC3 payload: endpoints
    byte-swapped, channels taken as DISPLAY RGBA (no shader)."""
    sw = bytearray(payload)
    for o in range(0, len(sw), 16):
        sw[o + 8], sw[o + 9], sw[o + 10], sw[o + 11] = sw[o + 9], sw[o + 8], sw[o + 11], sw[o + 10]
    return _decode_blocks("BC3", bytes(sw), n)


def _palette_fit(pixels: np.ndarray, palette: np.ndarray) -> float:
    """Mean distance from covered pixels to the nearest palette colour."""
    if len(pixels) == 0 or len(palette) == 0:
        return 0.0
    d = np.sqrt(((pixels[:, None, :3].astype(float) - palette[None, :, :3]) ** 2).sum(2)).min(1)
    return float(d.mean())


def scan_against_reference(eng: bytes, ref: bytes) -> dict:
    """Compare a live ENG XET with a reference (JPN/pristine/backup) of the
    same shape. For YCbCr formats, each changed block is judged against the
    colours of the UNCHANGED (trusted) art under two readings: the certified
    one, and the legacy xetenc reading (swapped endpoints, no shader). A block
    whose legacy reading fits the sheet far better than its certified reading
    was almost certainly written by the legacy tool and renders wrong in game."""
    a, b = xet_info(eng), xet_info(ref)
    if (a.width, a.height, a.format_code, a.mip_count) != (b.width, b.height, b.format_code, b.mip_count):
        return {"comparable": False}
    _require_read(a, 0)
    size = surface_bytes(a.codec, a.width, a.height)
    bs = 8 if a.codec == "BC1" else 16
    pa = bytes(eng[a.mip_offsets[0]:a.mip_offsets[0] + size])
    pb = bytes(ref[b.mip_offsets[0]:b.mip_offsets[0] + size])
    n = size // bs
    changed = [k for k in range(n) if pa[k * bs:(k + 1) * bs] != pb[k * bs:(k + 1) * bs]]
    res = {"comparable": True, "format": f"0x{a.format_code:02X}", "blocks_total": n,
           "blocks_changed": len(changed), "suspect_blocks": [], "suspect_legacy_encoding": False}
    if not (a.semantics.startswith("ycbcr") and changed):
        return res
    good = storage_to_display(_decode_blocks("BC3", pa, n).reshape(-1, 4)).reshape(n, 16, 4)
    legacy = _legacy_view(pa, n)
    unchanged = np.setdiff1d(np.arange(n), changed)
    pal = good[unchanged].reshape(-1, 4)
    pal = pal[pal[:, 3] > 32]
    if len(pal):
        pal = np.unique((pal[:, :3] // 8) * 8 + 4, axis=0)
        if len(pal) > 512:
            pal = pal[np.random.default_rng(0).choice(len(pal), 512, replace=False)]
    bw = (a.width + 3) // 4
    for k in changed:
        g_px = good[k][good[k][:, 3] > 32]
        l_px = legacy[k][legacy[k][:, 3] > 32]
        fg, fl = _palette_fit(g_px, pal), _palette_fit(l_px, pal)
        if len(g_px) >= 4 and fg > 40 and fl < 0.5 * fg:
            res["suspect_blocks"].append({"block": [k // bw, k % bw], "certified_fit": round(fg, 1),
                                          "legacy_fit": round(fl, 1)})
    res["suspect_share"] = round(len(res["suspect_blocks"]) / len(changed), 4)
    res["suspect_legacy_encoding"] = res["suspect_share"] >= 0.25
    res["whole_texture_byte_order"] = byte_order_evidence(eng)
    return res
