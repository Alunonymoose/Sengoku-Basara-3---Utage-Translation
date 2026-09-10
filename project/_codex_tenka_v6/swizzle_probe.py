from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")


def parse_xet(path: Path) -> tuple[bytes, int, int, str]:
    raw = path.read_bytes()
    if raw[:4] != b"\x00XET":
        raise ValueError(path)
    dimensions = struct.unpack_from(">I", raw, 8)[0]
    metadata = struct.unpack_from(">I", raw, 12)[0]
    width = (dimensions >> 19) & 0x1FFF
    height = (dimensions >> 6) & 0x1FFF
    mips = dimensions & 0x3F
    format_code = (metadata >> 8) & 0xFF
    fourcc = "DXT1" if format_code == 0x19 else "DXT5"
    data_offset = 20 + max(0, mips - 1) * 4
    if mips > 1:
        candidate = struct.unpack_from(">I", raw, 20)[0]
        if candidate < len(raw):
            data_offset = candidate
    payload_size = width * height // (2 if fourcc == "DXT1" else 1)
    return raw[data_offset:data_offset + payload_size], width, height, fourcc


def dds_header(width: int, height: int, payload_size: int, fourcc: str) -> bytes:
    pixel_format = struct.pack("<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0)
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, payload_size, 0, 1)
        + b"\0" * 44
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )


def morton(x: int, y: int) -> int:
    value = 0
    output_bit = 0
    bit = 0
    while (1 << bit) <= max(x, y):
        value |= ((x >> bit) & 1) << output_bit
        output_bit += 1
        value |= ((y >> bit) & 1) << output_bit
        output_bit += 1
        bit += 1
    return value


def reorder(payload: bytes, width: int, height: int, block_size: int, reverse: bool) -> bytes:
    blocks_w = max(1, (width + 3) // 4)
    blocks_h = max(1, (height + 3) // 4)
    coords = sorted(((x, y) for y in range(blocks_h) for x in range(blocks_w)), key=lambda p: morton(*p))
    source = [payload[i:i + block_size] for i in range(0, len(payload), block_size)]
    output = [b"\0" * block_size for _ in source]
    for stream_index, (x, y) in enumerate(coords):
        linear_index = y * blocks_w + x
        if reverse:
            output[stream_index] = source[linear_index]
        else:
            output[linear_index] = source[stream_index]
    return b"".join(output)


def write_candidates(path: Path) -> None:
    payload, width, height, fourcc = parse_xet(path)
    block_size = 8 if fourcc == "DXT1" else 16
    for mode, candidate in (
        ("linear", payload),
        ("morton_unswizzle", reorder(payload, width, height, block_size, False)),
        ("morton_reverse", reorder(payload, width, height, block_size, True)),
    ):
        dds_path = ROOT / f"{path.stem}_{mode}.dds"
        png_path = ROOT / f"{path.stem}_{mode}.png"
        dds_path.write_bytes(dds_header(width, height, len(candidate), fourcc) + candidate)
        Image.open(dds_path).convert("RGBA").save(png_path)
        print(png_path)


for name in ("cur_tenka_005.xet", "cur_tenka_029.xet", "sh_tenka_025.xet"):
    write_candidates(ROOT / name)
