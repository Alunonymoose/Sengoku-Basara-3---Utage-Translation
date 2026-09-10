"""Kuriimu2-compatible MT Framework PS3 XET codec for Alrummi 3.

The old Alrummi decoder treated the BC payload as final RGBA.  That is wrong
for at least PS3 format 0x2A: Kuriimu2 applies MT Framework's YCbCr colour
shader after BC3 decode, and applies the inverse shader before write.  The
result of skipping that step is the familiar raw green/magenta-looking UI art.

This module deliberately mirrors the *behaviour* established by Kuriimu2's
public MtTexSupport.cs while keeping Alrummi's conservative write policy:
- strict PS3 format table (with a few Utage-observed compatibility codes);
- exact header bit fields;
- the 0x2A YCbCr display/storage transforms;
- 0x21 no-alpha display transform;
- block-local writes so untouched BC blocks stay byte-identical;
- mip offsets from the PS3 XET offset table;
- unsupported formats fail loudly rather than being guessed as DXT5.

Reference behaviour:
  FanTranslatorsInternational/Kuriimu2
  plugins/Capcom/plugin_mt_framework/Images/MtTexSupport.cs
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import struct
from typing import Iterable

import numpy as np
from PIL import Image

import bcn
from alrummi3_core import Region


# Kuriimu2 PS3 table.  The compatibility entries are retained because real
# Utage samples in this project use them; unlike the old decoder they are
# explicit, not a catch-all "unknown means DXT5" fallback.
PS3_FORMATS: dict[int, str] = {
    0x13: "DXT1",
    0x14: "DXT3",
    0x17: "DXT5",
    0x19: "DXT1",
    0x1F: "DXT5",
    0x21: "DXT5",
    0x27: "DXT5",
    0x2A: "DXT5",
    # Utage-observed compatibility codes.  Keep these visible as such in
    # diagnostics rather than pretending Kuriimu2 documents them.
    0x15: "DXT5",
    0x18: "DXT5",
    0x2B: "DXT5",
}
COMPATIBILITY_CODES = {0x15, 0x18, 0x2B}
WRITABLE_FOURCC = {"DXT1", "DXT5"}
CBCR_ZERO = 123.0  # same empirical centre Kuriimu2 uses


@dataclass(frozen=True)
class MtTexInfo:
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
    compatibility_format: bool = False

    @property
    def shader(self) -> str:
        if self.format_code == 0x2A:
            return "MT YCbCr"
        if self.format_code == 0x21:
            return "MT no-alpha"
        return "none"

    @property
    def writable(self) -> bool:
        return self.fourcc in WRITABLE_FOURCC

    def mip_size(self, level: int) -> tuple[int, int, int]:
        w = max(1, self.width >> level)
        h = max(1, self.height >> level)
        block = 8 if self.fourcc == "DXT1" else 16
        size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
        return w, h, size

    def as_dict(self) -> dict:
        return {
            "container": "XET",
            "platform": "PS3",
            "version": f"0x{self.version:X2}",
            "format_code": f"0x{self.format_code:02X}",
            "format": self.fourcc,
            "width": self.width,
            "height": self.height,
            "mip_count": self.mip_count,
            "image_count": self.image_count,
            "alpha_flags": self.alpha_flags,
            "swizzle_field": self.swizzle_field,
            "display_shader": self.shader,
            "writable": self.writable,
            "compatibility_format": self.compatibility_format,
            "codec": "Kuriimu2 parity",
        }


def parse_xet(raw: bytes) -> MtTexInfo:
    if len(raw) < 20 or raw[:4] != b"\0XET":
        raise ValueError("not a PS3 MT Framework XET texture")

    # Kuriimu2 MtTexHeader uses LSB-first bit fields within a 4-byte block.
    # The PS3 stream itself is big-endian, so read each block as >I and peel
    # the fields from least-significant to most-significant bits.
    word4, word8, word12 = struct.unpack_from(">III", raw, 4)
    version = word4 & 0xFFF
    swizzle_field = (word4 >> 12) & 0xFFF
    alpha_flags = (word4 >> 28) & 0xF
    mip_count = word8 & 0x3F
    width = (word8 >> 6) & 0x1FFF
    height = (word8 >> 19) & 0x1FFF
    image_count = word12 & 0xFF
    format_code = (word12 >> 8) & 0xFF
    unk3 = (word12 >> 16) & 0xFFFF

    if version not in (0x97, 0x9A, 0x9D):
        raise ValueError(f"XET version 0x{version:X} is not a known PS3 MT texture")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid XET dimensions {width}x{height}")
    if image_count != 1:
        raise ValueError(
            f"PS3 XET contains {image_count} images; Alrummi Next currently supports one-image textures"
        )
    if mip_count <= 0:
        mip_count = 1
    fourcc = PS3_FORMATS.get(format_code)
    if fourcc is None:
        raise ValueError(
            f"unsupported PS3 MT texture format 0x{format_code:02X}; refusing to guess its encoding"
        )

    table_end = 16 + mip_count * 4
    if table_end > len(raw):
        raise ValueError("XET mip offset table is truncated")
    offsets = struct.unpack_from(">" + "I" * mip_count, raw, 16)
    previous = -1
    for level, offset in enumerate(offsets):
        _w, _h, size = _mip_geometry(width, height, fourcc, level)
        if offset < table_end or offset + size > len(raw):
            raise ValueError(
                f"mip {level} points outside XET: offset=0x{offset:X}, size=0x{size:X}"
            )
        if offset <= previous:
            raise ValueError("XET mip offsets are not strictly increasing")
        previous = offset

    return MtTexInfo(
        version=version,
        swizzle_field=swizzle_field,
        alpha_flags=alpha_flags,
        mip_count=mip_count,
        width=width,
        height=height,
        image_count=image_count,
        format_code=format_code,
        fourcc=fourcc,
        unk3=unk3,
        mip_offsets=tuple(int(v) for v in offsets),
        compatibility_format=format_code in COMPATIBILITY_CODES,
    )


def _mip_geometry(width: int, height: int, fourcc: str, level: int) -> tuple[int, int, int]:
    w = max(1, width >> level)
    h = max(1, height >> level)
    block = 8 if fourcc == "DXT1" else 16
    return w, h, max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block


def _dds_header(width: int, height: int, size: int, fourcc: str) -> bytes:
    pixel_format = struct.pack(
        "<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0
    )
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, size, 0, 1)
        + b"\0" * 44
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )


def _decode_bc(payload: bytes, width: int, height: int, fourcc: str) -> Image.Image:
    dds = _dds_header(width, height, len(payload), fourcc) + payload
    try:
        with Image.open(io.BytesIO(dds)) as opened:
            result = opened.convert("RGBA")
            result.load()
            return result
    except Exception as exc:
        raise ValueError(f"Pillow could not decode {fourcc}: {exc}") from exc


def storage_to_display(array: np.ndarray, format_code: int) -> np.ndarray:
    """Apply the same PS3 colour shader Kuriimu2 applies after BC decode."""
    src = np.asarray(array, dtype=np.float32)
    if src.ndim != 3 or src.shape[2] != 4:
        raise ValueError("expected an RGBA array")

    if format_code == 0x2A:
        # Kuriimu2 MtTex_YCbCrColorShader.Read:
        #   a=G, y=A, cb=B-123, cr=R-123
        # followed by JPEG YCbCr -> RGB conversion.
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


def display_to_storage(array: np.ndarray, format_code: int) -> np.ndarray:
    """Inverse of the Kuriimu2 display shader, used before BC encoding."""
    src = np.asarray(array, dtype=np.float32)
    if src.ndim != 3 or src.shape[2] != 4:
        raise ValueError("expected an RGBA array")

    if format_code == 0x2A:
        r, g, b, a = src[..., 0], src[..., 1], src[..., 2], src[..., 3]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cb = CBCR_ZERO - 0.168736 * r - 0.331264 * g + 0.5 * b
        cr = CBCR_ZERO + 0.5 * r - 0.418688 * g - 0.081312 * b
        out = np.empty_like(src)
        # Color.FromArgb(y, cr, a, cb) in Kuriimu2's Write method means
        # storage RGBA=(Cr, display alpha, Cb, Y).
        out[..., 0] = cr
        out[..., 1] = a
        out[..., 2] = cb
        out[..., 3] = y
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)

    return np.clip(np.rint(src), 0, 255).astype(np.uint8)


def decode_xet(raw: bytes, *, level: int = 0) -> tuple[Image.Image, MtTexInfo]:
    info = parse_xet(raw)
    if not 0 <= level < info.mip_count:
        raise ValueError(f"mip level {level} is outside 0..{info.mip_count - 1}")
    width, height, size = info.mip_size(level)
    offset = info.mip_offsets[level]
    storage = _decode_bc(raw[offset:offset + size], width, height, info.fourcc)
    pixels = storage_to_display(np.asarray(storage, dtype=np.uint8), info.format_code)
    return Image.fromarray(pixels, "RGBA"), info


def changed_bbox(source: Image.Image, candidate: Image.Image) -> Region | None:
    if source.size != candidate.size:
        raise ValueError("source and candidate dimensions differ")
    a = np.asarray(source.convert("RGBA"), dtype=np.int16)
    b = np.asarray(candidate.convert("RGBA"), dtype=np.int16)
    changed = np.any(a != b, axis=2)
    if not changed.any():
        return None
    ys, xs = np.nonzero(changed)
    return Region(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _copy_block_region(
    output: bytearray,
    encoded: bytes,
    *,
    offset: int,
    width: int,
    height: int,
    block_bytes: int,
    region: Region,
) -> int:
    box = region.clipped((width, height))
    blocks_w = max(1, (width + 3) // 4)
    blocks_h = max(1, (height + 3) // 4)
    left = box.left // 4
    top = box.top // 4
    right = min(blocks_w, (box.right + 3) // 4)
    bottom = min(blocks_h, (box.bottom + 3) // 4)
    touched = 0
    for by in range(top, bottom):
        first_block = by * blocks_w + left
        count = max(0, right - left)
        if not count:
            continue
        src = first_block * block_bytes
        span = count * block_bytes
        dst = offset + src
        output[dst:dst + span] = encoded[src:src + span]
        touched += count
    return touched


def encode_candidate(
    raw: bytes,
    candidate: Image.Image,
    *,
    region: Region | None = None,
    rebuild_mips: bool = True,
) -> tuple[bytes, dict]:
    """Encode a reviewed display-space candidate back into an XET safely.

    Only blocks touched by the changed display-space bounding box are replaced.
    That is particularly important for UI atlases: a one-label repair should
    not recompress unrelated icons on the same sheet.
    """
    source, info = decode_xet(raw)
    candidate = candidate.convert("RGBA")
    if candidate.size != source.size:
        raise ValueError(
            f"candidate is {candidate.size}, expected {(info.width, info.height)}"
        )
    if not info.writable:
        raise ValueError(
            f"{info.fourcc} / format 0x{info.format_code:02X} is preview-only; use a lossless donor swap"
        )

    box = region.clipped(source.size) if region else changed_bbox(source, candidate)
    if box is None:
        raise ValueError("candidate is pixel-identical to the source; there is nothing to write")

    block_bytes = 8 if info.fourcc == "DXT1" else 16
    output = bytearray(raw)
    total_blocks = 0

    storage = display_to_storage(np.asarray(candidate, dtype=np.uint8), info.format_code)
    encoded = bcn.encode(storage, info.fourcc)
    total_blocks += _copy_block_region(
        output,
        encoded,
        offset=info.mip_offsets[0],
        width=info.width,
        height=info.height,
        block_bytes=block_bytes,
        region=box,
    )

    if rebuild_mips and info.mip_count > 1:
        for level in range(1, info.mip_count):
            width, height, _size = info.mip_size(level)
            resized = candidate.resize((width, height), Image.Resampling.LANCZOS)
            level_storage = display_to_storage(
                np.asarray(resized, dtype=np.uint8), info.format_code
            )
            level_encoded = bcn.encode(level_storage, info.fourcc)
            scale = 1 << level
            level_box = Region(
                box.left // scale,
                box.top // scale,
                max(box.left // scale + 1, (box.right + scale - 1) // scale),
                max(box.top // scale + 1, (box.bottom + scale - 1) // scale),
            ).clipped((width, height))
            total_blocks += _copy_block_region(
                output,
                level_encoded,
                offset=info.mip_offsets[level],
                width=width,
                height=height,
                block_bytes=block_bytes,
                region=level_box,
            )

    return bytes(output), {
        **info.as_dict(),
        "changed_region": box.as_list(),
        "bc_blocks_replaced": total_blocks,
        "display_to_storage_shader": info.shader,
    }


def compare_images(a: Image.Image, b: Image.Image) -> dict:
    """Pixel diagnostics for comparing an Alrummi render with a Kuriimu PNG."""
    if a.size != b.size:
        return {"dimensions_match": False, "a": list(a.size), "b": list(b.size)}
    aa = np.asarray(a.convert("RGBA"), dtype=np.int16)
    bb = np.asarray(b.convert("RGBA"), dtype=np.int16)
    diff = np.abs(aa - bb)
    return {
        "dimensions_match": True,
        "mean_abs_error": round(float(diff.mean()), 4),
        "max_abs_error": int(diff.max()),
        "pixels_exact": round(float(np.all(diff == 0, axis=2).mean()) * 100.0, 3),
    }
