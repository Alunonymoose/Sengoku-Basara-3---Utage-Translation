"""Kuriimu2-parity MT Framework PS3 XET codec used by the hybrid Alrummi UI.

The original Alrummi decoder treated the decompressed BC payload as display
RGBA.  That is not correct for all MT Framework PS3 textures.  In particular,
format 0x2A is BC3/DXT5 storage plus Capcom's YCbCr colour shader:

    display alpha = stored G
    display Y     = stored A
    display Cb    = stored B - 123
    display Cr    = stored R - 123

Kuriimu2 applies that transform on read and the inverse transform on write.
This module mirrors that behaviour and deliberately refuses to guess unknown
formats.  Writes are conservative: only BC blocks touched by the requested
region are replaced in mip 0, while stored lower mips are rebuilt when present.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import math
import struct

import numpy as np
from PIL import Image, ImageChops

import bcn
from alrummi3_core import Region


PS3_FORMATS: dict[int, str] = {
    0x13: "DXT1",
    0x14: "DXT3",
    0x17: "DXT5",
    0x19: "DXT1",
    0x1F: "DXT5",
    0x21: "DXT5",
    0x27: "DXT5",
    0x2A: "DXT5",
    # Seen in project samples.  These stay explicit so an unknown code never
    # silently becomes DXT5.
    0x15: "DXT5",
    0x18: "DXT5",
    0x2B: "DXT5",
}
COMPATIBILITY_CODES = {0x15, 0x18, 0x2B}
WRITABLE_FOURCC = {"DXT1", "DXT5"}
CBCR_ZERO = 123.0


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
        return _mip_geometry(self.width, self.height, self.fourcc, level)

    def as_dict(self) -> dict:
        return {
            "container": "XET",
            "platform": "PS3",
            "version": f"0x{self.version:02X}",
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


def _mip_geometry(width: int, height: int, fourcc: str, level: int) -> tuple[int, int, int]:
    w = max(1, width >> level)
    h = max(1, height >> level)
    block = 8 if fourcc == "DXT1" else 16
    return w, h, max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block


def parse_xet(raw: bytes) -> MtTexInfo:
    if len(raw) < 20 or raw[:4] != b"\0XET":
        raise ValueError("not a PS3 MT Framework XET texture")

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
        raise ValueError(f"unsupported PS3 MT texture version 0x{version:X}")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid XET dimensions {width}x{height}")
    if image_count not in (0, 1):
        raise ValueError(f"XET contains {image_count} images; multi-image PS3 XET is not supported")
    image_count = max(1, image_count)
    mip_count = max(1, mip_count)

    fourcc = PS3_FORMATS.get(format_code)
    if fourcc is None:
        raise ValueError(
            f"unsupported PS3 MT texture format 0x{format_code:02X}; refusing to guess"
        )

    table_end = 16 + mip_count * 4
    if table_end > len(raw):
        raise ValueError("XET mip offset table is truncated")
    offsets = tuple(struct.unpack_from(">" + "I" * mip_count, raw, 16))

    previous = -1
    for level, offset in enumerate(offsets):
        _w, _h, size = _mip_geometry(width, height, fourcc, level)
        if offset < table_end or offset + size > len(raw):
            raise ValueError(
                f"mip {level} outside resource: offset=0x{offset:X}, size=0x{size:X}, len=0x{len(raw):X}"
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
        mip_offsets=offsets,
        compatibility_format=format_code in COMPATIBILITY_CODES,
    )


def _dds_header(width: int, height: int, payload_size: int, fourcc: str) -> bytes:
    pixel_format = struct.pack(
        "<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0
    )
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, payload_size, 0, 1)
        + b"\0" * 44
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )


def _decode_bc(payload: bytes, width: int, height: int, fourcc: str) -> Image.Image:
    dds = _dds_header(width, height, len(payload), fourcc) + payload
    try:
        with Image.open(io.BytesIO(dds)) as opened:
            image = opened.convert("RGBA")
            image.load()
            return image
    except Exception as exc:
        raise ValueError(f"Pillow could not decode {fourcc}: {exc}") from exc


def storage_to_display(array: np.ndarray, format_code: int) -> np.ndarray:
    src = np.asarray(array, dtype=np.float32)
    if src.ndim != 3 or src.shape[2] != 4:
        raise ValueError("expected RGBA pixels")

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


def display_to_storage(array: np.ndarray, format_code: int) -> np.ndarray:
    src = np.asarray(array, dtype=np.float32)
    if src.ndim != 3 or src.shape[2] != 4:
        raise ValueError("expected RGBA pixels")

    if format_code == 0x2A:
        r, g, b, a = src[..., 0], src[..., 1], src[..., 2], src[..., 3]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cb = CBCR_ZERO - 0.168736 * r - 0.331264 * g + 0.5 * b
        cr = CBCR_ZERO + 0.5 * r - 0.418688 * g - 0.081312 * b
        out = np.empty_like(src)
        # Kuriimu2 Color.FromArgb(y, cr, a, cb) -> stored RGBA=(Cr,A,Cb,Y).
        out[..., 0] = cr
        out[..., 1] = a
        out[..., 2] = cb
        out[..., 3] = y
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)

    return np.clip(np.rint(src), 0, 255).astype(np.uint8)


def decode_xet(raw: bytes, *, level: int = 0) -> tuple[Image.Image, MtTexInfo]:
    info = parse_xet(raw)
    if not 0 <= level < info.mip_count:
        raise ValueError(f"mip {level} outside 0..{info.mip_count - 1}")
    width, height, size = info.mip_size(level)
    offset = info.mip_offsets[level]
    storage = _decode_bc(raw[offset:offset + size], width, height, info.fourcc)
    pixels = storage_to_display(np.asarray(storage, dtype=np.uint8), info.format_code)
    return Image.fromarray(pixels, "RGBA"), info


def decode_resource(raw: bytes, name: str = "") -> tuple[Image.Image, dict]:
    if raw[:4] != b"\0XET":
        raise ValueError("mttex_codec only handles XET resources")
    image, info = decode_xet(raw)
    return image, info.as_dict()


def changed_bbox(source: Image.Image, candidate: Image.Image) -> Region | None:
    if source.size != candidate.size:
        raise ValueError("source and candidate dimensions differ")
    diff = ImageChops.difference(source.convert("RGBA"), candidate.convert("RGBA"))
    box = diff.getbbox()
    if box is None:
        return None
    return Region(*box)


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
    for block_y in range(top, bottom):
        first = block_y * blocks_w + left
        count = max(0, right - left)
        if not count:
            continue
        src = first * block_bytes
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
    source, info = decode_xet(raw)
    candidate = candidate.convert("RGBA")
    if candidate.size != source.size:
        raise ValueError(f"candidate size {candidate.size} != source size {source.size}")
    if not info.writable:
        raise ValueError(
            f"{info.fourcc}/0x{info.format_code:02X} is preview-only in Alrummi; use a lossless donor"
        )

    box = region.clipped(source.size) if region else changed_bbox(source, candidate)
    if box is None:
        raise ValueError("candidate is pixel-identical to source")

    block_bytes = 8 if info.fourcc == "DXT1" else 16
    storage = display_to_storage(np.asarray(candidate, dtype=np.uint8), info.format_code)
    encoded = bcn.encode(storage, info.fourcc)
    output = bytearray(raw)
    touched = _copy_block_region(
        output,
        encoded,
        offset=info.mip_offsets[0],
        width=info.width,
        height=info.height,
        block_bytes=block_bytes,
        region=box,
    )

    if rebuild_mips and info.mip_count > 1:
        # A Japanese lower mip can reappear when the UI scales down.  Rebuild
        # stored lower levels from the reviewed candidate.
        for level in range(1, info.mip_count):
            width, height, size = info.mip_size(level)
            resized = candidate.resize((width, height), Image.Resampling.LANCZOS)
            level_storage = display_to_storage(
                np.asarray(resized, dtype=np.uint8), info.format_code
            )
            blob = bcn.encode(level_storage, info.fourcc)
            offset = info.mip_offsets[level]
            output[offset:offset + size] = blob[:size]

    return bytes(output), {
        "codec": "Kuriimu2 parity",
        "format_code": f"0x{info.format_code:02X}",
        "format": info.fourcc,
        "display_shader": info.shader,
        "changed_region": box.as_list(),
        "top_mip_blocks_reencoded": touched,
        "mips_rebuilt": info.mip_count if rebuild_mips else 1,
    }


def compare_with_png(raw: bytes, png: Image.Image) -> dict:
    """Pixel comparison against a Kuriimu2 PNG export."""
    ours, info = decode_xet(raw)
    theirs = png.convert("RGBA")
    if theirs.size != ours.size:
        raise ValueError(f"reference PNG is {theirs.size}; texture is {ours.size}")
    a = np.asarray(ours, dtype=np.int16)
    b = np.asarray(theirs, dtype=np.int16)
    delta = np.abs(a - b)
    return {
        "dimensions": list(ours.size),
        "format_code": f"0x{info.format_code:02X}",
        "display_shader": info.shader,
        "max_channel_error": int(delta.max()),
        "mean_channel_error": float(delta.mean()),
        "pixels_exact": int(np.all(a == b, axis=2).sum()),
        "pixel_count": int(ours.width * ours.height),
    }
