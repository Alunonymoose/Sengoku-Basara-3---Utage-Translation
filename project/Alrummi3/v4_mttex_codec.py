"""PS3 MT Framework XET codec for Alrummi 3 V4.

Display/write behaviour follows the Kuriimu2 PS3 texture path used by this
project.  In particular format 0x2A is BC3 storage with MT's YCbCr channel
shader, not final RGBA.  The inverse transform is applied before encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import struct

import numpy as np
from PIL import Image

import bcn
from alrummi3_core import Region

PS3_FORMATS = {
    0x13: "DXT1",
    0x14: "DXT3",
    0x15: "DXT5",
    0x17: "DXT5",
    0x18: "DXT5",
    0x19: "DXT1",
    0x1F: "DXT5",
    0x21: "DXT5",
    0x27: "DXT5",
    0x2A: "DXT5",
    0x2B: "DXT5",
}
WRITABLE = {"DXT1", "DXT5"}
CBCR_ZERO = 123.0

@dataclass(frozen=True)
class XetInfo:
    version: int
    swizzle_field: int
    alpha_flags: int
    mip_count: int
    width: int
    height: int
    image_count: int
    format_code: int
    fourcc: str
    unk3: int
    mip_offsets: tuple[int, ...]

    @property
    def shader(self) -> str:
        if self.format_code == 0x2A:
            return "MT YCbCr"
        if self.format_code == 0x21:
            return "MT no-alpha"
        return "none"

    @property
    def writable(self) -> bool:
        return self.fourcc in WRITABLE

    def mip_size(self, level: int) -> tuple[int, int, int]:
        w = max(1, self.width >> level)
        h = max(1, self.height >> level)
        block = 8 if self.fourcc == "DXT1" else 16
        return w, h, max(1, (w + 3)//4) * max(1, (h + 3)//4) * block

    def as_dict(self) -> dict:
        return {
            "container": "XET",
            "format": self.fourcc,
            "format_code": f"0x{self.format_code:02X}",
            "version": f"0x{self.version:02X}",
            "width": self.width,
            "height": self.height,
            "mip_levels": self.mip_count,
            "display_shader": self.shader,
            "writable": self.writable,
            "codec": "Kuriimu2-compatible PS3",
        }

def _mip_geometry(width: int, height: int, fourcc: str, level: int):
    w = max(1, width >> level)
    h = max(1, height >> level)
    block = 8 if fourcc == "DXT1" else 16
    return w, h, max(1, (w + 3)//4) * max(1, (h + 3)//4) * block

def parse_xet(raw: bytes) -> XetInfo:
    if len(raw) < 20 or raw[:4] != b"\0XET":
        raise ValueError("not a PS3 MT Framework XET texture")

    word4, word8, word12 = struct.unpack_from(">III", raw, 4)
    version = word4 & 0xFFF
    swizzle = (word4 >> 12) & 0xFFF
    alpha_flags = (word4 >> 28) & 0xF
    mip_count = word8 & 0x3F
    width = (word8 >> 6) & 0x1FFF
    height = (word8 >> 19) & 0x1FFF
    image_count = word12 & 0xFF
    fmt = (word12 >> 8) & 0xFF
    unk3 = (word12 >> 16) & 0xFFFF

    if version not in (0x97, 0x9A, 0x9D):
        raise ValueError(f"unsupported PS3 XET version 0x{version:X}")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid XET dimensions {width}x{height}")
    if image_count != 1:
        raise ValueError(f"XET contains {image_count} images; V4 currently supports one")
    mip_count = max(1, mip_count)
    fourcc = PS3_FORMATS.get(fmt)
    if fourcc is None:
        raise ValueError(f"unsupported PS3 XET format 0x{fmt:02X}")

    table_end = 16 + 4 * mip_count
    if table_end > len(raw):
        raise ValueError("XET mip table is truncated")
    offsets = struct.unpack_from(">" + "I"*mip_count, raw, 16)
    previous = -1
    for level, off in enumerate(offsets):
        _, _, size = _mip_geometry(width, height, fourcc, level)
        if off < table_end or off + size > len(raw):
            raise ValueError(
                f"mip {level} outside XET (offset 0x{off:X}, size 0x{size:X}, file 0x{len(raw):X})"
            )
        if off <= previous:
            raise ValueError("XET mip offsets are not increasing")
        previous = off

    return XetInfo(
        version, swizzle, alpha_flags, mip_count, width, height,
        image_count, fmt, fourcc, unk3, tuple(int(x) for x in offsets)
    )

def _dds_header(width: int, height: int, size: int, fourcc: str) -> bytes:
    pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0)
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, size, 0, 1)
        + b"\0"*44 + pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )

def _decode_bc(payload: bytes, width: int, height: int, fourcc: str) -> Image.Image:
    try:
        with Image.open(io.BytesIO(_dds_header(width, height, len(payload), fourcc) + payload)) as im:
            out = im.convert("RGBA")
            out.load()
            return out
    except Exception as exc:
        raise ValueError(f"could not decode {fourcc}: {exc}") from exc

def storage_to_display(rgba: np.ndarray, format_code: int) -> np.ndarray:
    src = np.asarray(rgba, dtype=np.float32)
    if format_code == 0x2A:
        y = src[..., 3]
        cb = src[..., 2] - CBCR_ZERO
        cr = src[..., 0] - CBCR_ZERO
        out = np.empty_like(src)
        out[..., 0] = y + 1.402 * cr
        out[..., 1] = y - 0.344136 * cb - 0.714136 * cr
        out[..., 2] = y + 1.772 * cb
        out[..., 3] = src[..., 1]
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    out = np.clip(np.rint(src), 0, 255).astype(np.uint8)
    if format_code == 0x21:
        out = out.copy()
        out[..., 3] = 255
    return out

def display_to_storage(rgba: np.ndarray, format_code: int) -> np.ndarray:
    src = np.asarray(rgba, dtype=np.float32)
    if format_code == 0x2A:
        r, g, b, a = src[...,0], src[...,1], src[...,2], src[...,3]
        y = 0.299*r + 0.587*g + 0.114*b
        cb = CBCR_ZERO - 0.168736*r - 0.331264*g + 0.5*b
        cr = CBCR_ZERO + 0.5*r - 0.418688*g - 0.081312*b
        out = np.empty_like(src)
        out[...,0] = cr
        out[...,1] = a
        out[...,2] = cb
        out[...,3] = y
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return np.clip(np.rint(src), 0, 255).astype(np.uint8)

def decode_xet(raw: bytes, level: int = 0):
    info = parse_xet(raw)
    if not 0 <= level < info.mip_count:
        raise ValueError("invalid mip level")
    w, h, size = info.mip_size(level)
    off = info.mip_offsets[level]
    storage = _decode_bc(raw[off:off+size], w, h, info.fourcc)
    display = storage_to_display(np.asarray(storage, dtype=np.uint8), info.format_code)
    return Image.fromarray(display, "RGBA"), info

def decode_resource(raw: bytes, name: str = ""):
    if raw[:4] == b"\0XET":
        image, info = decode_xet(raw)
        return image, info.as_dict()
    try:
        with Image.open(io.BytesIO(raw)) as im:
            out = im.convert("RGBA")
            out.load()
        return out, {
            "container": "image", "format": "native image",
            "width": out.width, "height": out.height, "writable": True,
            "codec": "Pillow",
        }
    except Exception as exc:
        raise ValueError(f"unsupported texture/resource format: {exc}") from exc

def changed_bbox(source: Image.Image, candidate: Image.Image) -> Region | None:
    a = np.asarray(source.convert("RGBA"), dtype=np.int16)
    b = np.asarray(candidate.convert("RGBA"), dtype=np.int16)
    if a.shape != b.shape:
        raise ValueError("candidate dimensions changed")
    changed = np.any(a != b, axis=2)
    if not changed.any():
        return None
    ys, xs = np.nonzero(changed)
    return Region(int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1)

def _copy_blocks(output: bytearray, encoded: bytes, *, offset: int,
                 width: int, height: int, block_bytes: int, region: Region) -> int:
    box = region.clipped((width, height))
    bw = max(1, (width + 3)//4)
    bh = max(1, (height + 3)//4)
    left = box.left//4
    top = box.top//4
    right = min(bw, (box.right+3)//4)
    bottom = min(bh, (box.bottom+3)//4)
    touched = 0
    for by in range(top, bottom):
        first = by*bw + left
        count = max(0, right-left)
        if not count:
            continue
        src = first*block_bytes
        span = count*block_bytes
        dst = offset+src
        output[dst:dst+span] = encoded[src:src+span]
        touched += count
    return touched

def encode_candidate(raw: bytes, candidate: Image.Image, region: Region | None = None):
    source, info = decode_xet(raw)
    candidate = candidate.convert("RGBA")
    if candidate.size != source.size:
        raise ValueError(f"candidate size {candidate.size} != source size {source.size}")
    if not info.writable:
        raise ValueError(f"{info.fourcc} / 0x{info.format_code:02X} is preview-only")

    box = region.clipped(source.size) if region else changed_bbox(source, candidate)
    if box is None:
        raise ValueError("candidate is identical to source")

    output = bytearray(raw)
    block_bytes = 8 if info.fourcc == "DXT1" else 16

    storage = display_to_storage(np.asarray(candidate, dtype=np.uint8), info.format_code)
    encoded = bcn.encode(storage, info.fourcc)
    touched = _copy_blocks(
        output, encoded, offset=info.mip_offsets[0], width=info.width,
        height=info.height, block_bytes=block_bytes, region=box
    )

    # Rebuild lower mips so translated lettering does not revert at distance.
    for level in range(1, info.mip_count):
        w, h, _ = info.mip_size(level)
        resized = candidate.resize((w, h), Image.Resampling.LANCZOS)
        level_storage = display_to_storage(
            np.asarray(resized, dtype=np.uint8), info.format_code
        )
        blob = bcn.encode(level_storage, info.fourcc)
        output[info.mip_offsets[level]:info.mip_offsets[level]+len(blob)] = blob

    return bytes(output), {
        "format": info.fourcc,
        "format_code": f"0x{info.format_code:02X}",
        "shader": info.shader,
        "changed_region": box.as_list(),
        "top_mip_blocks_replaced": touched,
        "mips_rebuilt": info.mip_count,
    }

def swap_xet_payload(source_raw: bytes, donor_raw: bytes) -> bytes:
    source = parse_xet(source_raw)
    donor = parse_xet(donor_raw)
    sig_a = (source.width, source.height, source.format_code, source.mip_count)
    sig_b = (donor.width, donor.height, donor.format_code, donor.mip_count)
    if sig_a != sig_b:
        raise ValueError(f"donor XET layout {sig_b} != source {sig_a}")
    out = bytearray(source_raw)
    for level in range(source.mip_count):
        sw, sh, ss = source.mip_size(level)
        dw, dh, ds = donor.mip_size(level)
        if (sw, sh, ss) != (dw, dh, ds):
            raise ValueError(f"donor mip {level} differs")
        so = source.mip_offsets[level]
        do = donor.mip_offsets[level]
        out[so:so+ss] = donor_raw[do:do+ds]
    return bytes(out)
