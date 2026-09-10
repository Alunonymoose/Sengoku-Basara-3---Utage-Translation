from __future__ import annotations

import hashlib
import io
import json
import struct
from pathlib import Path

from PIL import Image

import arc_tools


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")
CURRENT_ARC = Path(
    r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng\tenka\tenka_id.arc"
)
OUTPUT_ARC = ROOT / "tenka_id_v6.arc"

STAGE_NODES = (108, 113, 118, 123, 128, 133, 137)
STAGE_SCALE_X = 0.54


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dds_header(width: int, height: int, payload_size: int, fourcc: str) -> bytes:
    pixel_format = struct.pack("<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0)
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, payload_size, 0, 1)
        + b"\0" * 44
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )


def xet_info(raw: bytes) -> dict[str, int | str]:
    if raw[:4] != b"\x00XET":
        raise ValueError("not an XET texture")
    packed_dimensions = int.from_bytes(b"\0" + raw[8:11], "big")
    width = (packed_dimensions & 0xFFF) * 4
    height = ((packed_dimensions >> 12) & 0xFFF) * 2
    texture_offset = struct.unpack_from(">I", raw, 16)[0]
    format_code = raw[14]
    fourcc = "DXT1" if format_code in (0x14, 0x19) else "DXT5"
    block_size = 8 if fourcc == "DXT1" else 16
    payload_size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
    if texture_offset + payload_size > len(raw):
        raise ValueError(
            f"XET payload overruns resource: {width}x{height}, offset=0x{texture_offset:X}"
        )
    return {
        "width": width,
        "height": height,
        "texture_offset": texture_offset,
        "format_code": format_code,
        "fourcc": fourcc,
        "block_size": block_size,
        "payload_size": payload_size,
    }


def decode_xet(raw: bytes) -> Image.Image:
    info = xet_info(raw)
    start = int(info["texture_offset"])
    end = start + int(info["payload_size"])
    dds = dds_header(
        int(info["width"]), int(info["height"]), int(info["payload_size"]), str(info["fourcc"])
    ) + raw[start:end]
    with Image.open(io.BytesIO(dds)) as decoded:
        image = decoded.convert("RGBA")
        image.load()
        return image


def rgb_to_565(color: tuple[int, int, int]) -> int:
    r, g, b = color
    return ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5) | ((b * 31 + 127) // 255)


def rgb_from_565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 31
    g = (value >> 5) & 63
    b = value & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def encode_bc3_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    if len(pixels) != 16:
        raise ValueError("BC3 block must contain 16 pixels")

    alphas = [pixel[3] for pixel in pixels]
    alpha0 = max(alphas)
    alpha1 = min(alphas)
    if alpha0 == alpha1:
        alpha_palette = [alpha0] * 8
    else:
        alpha_palette = [
            alpha0,
            alpha1,
            (6 * alpha0 + alpha1 + 3) // 7,
            (5 * alpha0 + 2 * alpha1 + 3) // 7,
            (4 * alpha0 + 3 * alpha1 + 3) // 7,
            (3 * alpha0 + 4 * alpha1 + 3) // 7,
            (2 * alpha0 + 5 * alpha1 + 3) // 7,
            (alpha0 + 6 * alpha1 + 3) // 7,
        ]
    alpha_bits = 0
    for index, alpha in enumerate(alphas):
        choice = min(range(8), key=lambda item: abs(alpha - alpha_palette[item]))
        alpha_bits |= choice << (index * 3)

    visible = [pixel[:3] for pixel in pixels if pixel[3] >= 16]
    if not visible:
        visible = [(0, 0, 0)]
    darkest = min(visible, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
    brightest = max(visible, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
    color0 = rgb_to_565(brightest)
    color1 = rgb_to_565(darkest)
    if color0 <= color1:
        if color1 < 0xFFFF:
            color0 = color1 + 1
        elif color0 > 0:
            color1 = color0 - 1
    c0 = rgb_from_565(color0)
    c1 = rgb_from_565(color1)
    palette = [
        c0,
        c1,
        tuple((2 * a + b + 1) // 3 for a, b in zip(c0, c1)),
        tuple((a + 2 * b + 1) // 3 for a, b in zip(c0, c1)),
    ]
    color_bits = 0
    for index, pixel in enumerate(pixels):
        if pixel[3] < 8:
            choice = 0
        else:
            choice = min(
                range(4),
                key=lambda item: sum((pixel[channel] - palette[item][channel]) ** 2 for channel in range(3)),
            )
        color_bits |= choice << (index * 2)

    return (
        bytes((alpha0, alpha1))
        + alpha_bits.to_bytes(6, "little")
        + struct.pack("<HHI", color0, color1, color_bits)
    )


def patch_bc3_rect(raw: bytes, image: Image.Image, rect: tuple[int, int, int, int]) -> bytes:
    info = xet_info(raw)
    if info["fourcc"] != "DXT5":
        raise ValueError("target texture is not BC3/DXT5")
    width = int(info["width"])
    height = int(info["height"])
    if image.size != (width, height):
        raise ValueError((image.size, width, height))
    left, top, right, bottom = rect
    left = max(0, left // 4 * 4)
    top = max(0, top // 4 * 4)
    right = min(width, (right + 3) // 4 * 4)
    bottom = min(height, (bottom + 3) // 4 * 4)
    blocks_w = (width + 3) // 4
    output = bytearray(raw)
    payload_start = int(info["texture_offset"])
    pixels = image.load()
    for block_y in range(top // 4, bottom // 4):
        for block_x in range(left // 4, right // 4):
            block_pixels = [
                pixels[min(width - 1, block_x * 4 + x), min(height - 1, block_y * 4 + y)]
                for y in range(4)
                for x in range(4)
            ]
            encoded = encode_bc3_block(block_pixels)
            offset = payload_start + (block_y * blocks_w + block_x) * 16
            output[offset:offset + 16] = encoded
    return bytes(output)


def clear(image: Image.Image, rect: tuple[int, int, int, int]) -> None:
    image.paste((0, 0, 0, 0), rect)


def threshold_alpha(image: Image.Image, threshold: int) -> Image.Image:
    result = image.copy()
    alpha = result.getchannel("A").point(lambda value: 0 if value < threshold else value)
    result.putalpha(alpha)
    return result


def edit_top_label(target_raw: bytes, donor_raw: bytes) -> tuple[bytes, dict]:
    target = decode_xet(target_raw)
    donor = decode_xet(donor_raw)
    donor_crop = threshold_alpha(donor.crop((657, 76, 911, 116)), 64)
    donor_crop = donor_crop.resize((144, 24), Image.Resampling.LANCZOS)
    clear_rect = (672, 96, 824, 128)
    clear(target, clear_rect)
    target.alpha_composite(donor_crop, (676, 100))
    edited = patch_bc3_rect(target_raw, target, clear_rect)
    decode_xet(edited).save(ROOT / "v6_top_quick_battles_preview.png")
    return edited, {
        "resource": "id\\texture\\jpn\\tenka\\tenka_005_ID_HQ",
        "change": "Free Battle header: 自由合戦 -> Quick Battles",
        "target_rect_physical": list(clear_rect),
        "donor_rect_physical": [657, 76, 911, 116],
        "rendered_label_size": [144, 24],
        "source": "official Samurai Heroes tenka_025_ID_HQ",
    }


def edit_battle_suffix(target_raw: bytes, donor_raw: bytes) -> tuple[bytes, dict]:
    target = decode_xet(target_raw)
    donor = decode_xet(donor_raw)
    donor_crop = donor.crop((7, 16, 180, 92))
    donor_crop = donor_crop.resize((82, 36), Image.Resampling.LANCZOS)
    clear_rect = (96, 0, 180, 64)
    clear(target, clear_rect)
    target.alpha_composite(donor_crop, (97, 14))
    edited = patch_bc3_rect(target_raw, target, clear_rect)
    decode_xet(edited).save(ROOT / "v6_battles_suffix_preview.png")
    return edited, {
        "resource": "id\\texture\\jpn\\tenka\\tenka_029_ID_HQ",
        "change": "Battle count suffix: 合戦 -> Battles",
        "target_rect_physical": list(clear_rect),
        "donor_rect_physical": [7, 16, 180, 92],
        "rendered_label_size": [82, 36],
        "source": "official Samurai Heroes tenka_011_ID_HQ",
    }


def edit_stage_layout(raw: bytes) -> tuple[bytes, dict]:
    if raw[:4] != b"\x00PSL":
        raise ValueError("stage layout owner is not PSL/LSP")
    output = bytearray(raw)
    before = []
    for index in STAGE_NODES:
        offset = 16 + index * 176 + 0x20
        old = struct.unpack_from(">f", output, offset)[0]
        before.append(old)
        struct.pack_into(">f", output, offset, STAGE_SCALE_X)
    return bytes(output), {
        "resource": "id\\lsp\\jpn\\tenka\\tenka_00",
        "change": "Free Battle stage-name horizontal fit",
        "nodes": list(STAGE_NODES),
        "scale_x_before": before,
        "scale_x_after": STAGE_SCALE_X,
        "scale_y_unchanged": True,
    }


def main() -> None:
    archive = arc_tools.parse_arc(CURRENT_ARC)
    target_029 = arc_tools.unpack(archive.entries[56])
    target_lsp = arc_tools.unpack(archive.entries[59])
    target_005 = arc_tools.unpack(archive.entries[67])
    donor_011 = (ROOT / "sh_tenka_011.xet").read_bytes()
    donor_025 = (ROOT / "sh_tenka_025.xet").read_bytes()

    edited_029, edit_029 = edit_battle_suffix(target_029, donor_011)
    edited_lsp, edit_lsp = edit_stage_layout(target_lsp)
    edited_005, edit_005 = edit_top_label(target_005, donor_025)
    replacements = {56: edited_029, 59: edited_lsp, 67: edited_005}
    rebuilt = arc_tools.rebuild(archive, replacements)
    OUTPUT_ARC.write_bytes(rebuilt)

    verified = arc_tools.parse_arc(OUTPUT_ARC)
    changed_entries = []
    for old, new in zip(archive.entries, verified.entries):
        old_raw = arc_tools.unpack(old)
        new_raw = arc_tools.unpack(new)
        if old_raw != new_raw:
            changed_entries.append({
                "index": new.index,
                "name": new.name,
                "type_hash": f"0x{new.type_hash:08X}",
                "old_raw_sha256": sha256(old_raw),
                "new_raw_sha256": sha256(new_raw),
                "old_raw_size": len(old_raw),
                "new_raw_size": len(new_raw),
            })
    if [row["index"] for row in changed_entries] != [56, 59, 67]:
        raise AssertionError(changed_entries)
    if any(arc_tools.unpack(entry)[:4] == b"" for entry in verified.entries):
        raise AssertionError("empty ARC resource")

    report = {
        "status": "pass",
        "input_arc": str(CURRENT_ARC),
        "output_arc": str(OUTPUT_ARC),
        "input_arc_sha256": sha256(archive.data),
        "output_arc_sha256": sha256(rebuilt),
        "entry_count": len(verified.entries),
        "changed_resource_count": len(changed_entries),
        "changed_resources": changed_entries,
        "edits": [edit_lsp, edit_005, edit_029],
        "xet_geometry_rule": "Capcom PS3 packed dimensions: width=low12*4, height=high12*2",
        "engine_smoke_test": "required",
    }
    (ROOT / "V6_TENKA_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
