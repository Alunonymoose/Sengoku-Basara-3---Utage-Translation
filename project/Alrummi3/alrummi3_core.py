"""Core archive, texture, and candidate-generation operations for Alrummi 3.

Alrummi 3 is intentionally small and conservative.  It understands the MT
Framework ARC v8 format used by Sengoku Basara 3 Utage and the XET textures
inside those archives.  It preserves untouched compressed blobs and changes
only the explicitly confirmed entry.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import bcn


ENTRY_SIZE = 80
EXTENDED_ENTRY_SIZE = 144
TABLE_START = 8
MSG_HASH = 0x10C460E6
FIM_HASH = 0x2EA515BF
CSA_HASH = 0x5E0EF076


@dataclass(frozen=True)
class ArcEntry:
    index: int
    name: str
    type_hash: int
    compressed_size: int
    raw_size: int
    flags: int
    packed_size: int
    payload_offset: int
    record: bytes
    compressed: bytes


@dataclass(frozen=True)
class ArcArchive:
    path: Path
    data: bytes
    endian: str
    magic: bytes
    version: int
    entries: tuple[ArcEntry, ...]
    table_start: int
    entry_size: int
    name_bytes: int
    payload_offset_field: int
    platform: str
    data_sha256: str


# MT Framework texture format codes.  The published PC/Switch table maps
# 0x13 to BC1, 0x15 to BC2, 0x17 to BC3 and 0x19 to BC4, but this is the
# big-endian PS3 build and it does not follow that table exactly.  These
# entries were each checked by decoding real textures every plausible way and
# looking at the result:
#
#   0x13  DXT1  - a model texture renders correctly as BC1 and as noise as
#                 BC4.  Previously mis-typed as DXT5, which made every 0x13
#                 texture fail to decode at all (28 of 28 in a survey).
#   0x19  DXT1  - a water alpha map renders coherently as BC1, as noise as
#                 BC4, so the PS3 build does not use the documented BC4 here.
#   0x2A  DXT5  - confirmed visually: BC2 gives dithered, broken alpha where
#                 BC3 gives the smooth alpha the artwork clearly intends.
#   0x15  ambiguous - BC2 and BC3 decode near-identically on the samples in
#                 this game, so it is left as BC3.  Both are 16 bytes per
#                 block, so a donor swap is byte-correct either way.
XET_FORMATS = {
    0x13: "DXT1",
    0x14: "DXT1",
    0x15: "DXT5",
    0x17: "DXT5",
    0x18: "DXT5",
    0x19: "DXT1",
    0x2A: "DXT5",
    0x2B: "DXT5",
}

# Only these may be re-encoded by the BC3 encoder.  Anything else is preview
# and lossless-donor-copy only.
# Every code whose block layout the encoder in `bcn` can produce.  DXT1 was
# blocked until the encoder existed; it is validated in `_bcn_validate.py` at
# a mean 63.8 dB against real game textures, so it is writable now.
BC3_WRITABLE = {0x17, 0x18, 0x2A, 0x2B}
WRITABLE_FORMATS = {"DXT1", "DXT5"}


@dataclass(frozen=True)
class XetInfo:
    width: int
    height: int
    texture_offset: int
    format_code: int
    fourcc: str
    block_size: int
    payload_size: int


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(1, self.right - self.left)

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    def clipped(self, size: tuple[int, int]) -> "Region":
        width, height = size
        return Region(
            max(0, min(self.left, width - 1)),
            max(0, min(self.top, height - 1)),
            max(1, min(self.right, width)),
            max(1, min(self.bottom, height)),
        )

    def as_list(self) -> list[int]:
        return [self.left, self.top, self.right, self.bottom]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_name(raw: bytes) -> str:
    raw = raw.split(b"\0", 1)[0]
    for encoding in ("utf-8", "shift_jis", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_arc(path: Path, *, metadata_only: bool = False) -> ArcArchive:
    path = Path(path)
    if metadata_only:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            data_prefix = stream.read(16)
            # The magic and count are read here so the header and the whole
            # entry table can be pulled in one go.  A recursive scan over a
            # large tree then costs a single open per archive instead of one
            # open per table read.
            if data_prefix[:4] == b"\0CRA":
                head_endian = ">"
            elif data_prefix[:4] == b"ARC\0":
                head_endian = "<"
            else:
                raise ValueError(f"unsupported ARC magic: {data_prefix[:4]!r}")
            if len(data_prefix) < 8:
                raise ValueError("ARC is shorter than its header")
            head_count = struct.unpack_from(head_endian + "H", data_prefix, 6)[0]
            head_span = min(file_size, TABLE_START + 4 + head_count * EXTENDED_ENTRY_SIZE)
            head = data_prefix + stream.read(max(0, head_span - len(data_prefix)))

        def read_range(offset: int, length: int) -> bytes:
            return head[offset : offset + length]

        data = b""
        # Batch indexing stays lightweight; the full hash is computed when an
        # archive is actually selected for decoding or writing.
        data_sha = ""
    else:
        data = path.read_bytes()
        file_size = len(data)
        data_prefix = data[:16]
        data_sha = sha256(data)

        def read_range(offset: int, length: int) -> bytes:
            return data[offset : offset + length]

    if data_prefix[:4] == b"\0CRA":
        endian = ">"
    elif data_prefix[:4] == b"ARC\0":
        endian = "<"
    else:
        raise ValueError(f"unsupported ARC magic: {data_prefix[:4]!r}")
    if len(data) < TABLE_START:
        if file_size < TABLE_START:
            raise ValueError("ARC is shorter than its header")
    version, count = struct.unpack_from(endian + "HH", data_prefix, 4)
    platform = "big-endian" if endian == ">" else ("switch" if version == 9 else "little-endian")
    table_start = TABLE_START + (4 if endian == "<" and version not in (7, 8, 9) else 0)
    entry_size = ENTRY_SIZE
    name_bytes = 64
    payload_offset_field = name_bytes + 12
    if endian == "<" and version == 9:
        # Kuriimu2's Switch entry has one extra u32 between size and offset.
        entry_size = 84
        payload_offset_field = 80
    elif endian == "<":
        if table_start + ENTRY_SIZE > file_size:
            raise ValueError("ARC entry table is truncated")
        first_record = read_range(table_start, ENTRY_SIZE)
        first_hash, _first_comp, first_packed, first_offset = struct.unpack_from(
            endian + "IIII", first_record, 64
        )
        if first_hash == 0 or first_packed == 0 or first_offset == 0:
            entry_size = EXTENDED_ENTRY_SIZE
            name_bytes = 128
        payload_offset_field = name_bytes + 12
    metadata_offset = name_bytes
    table_end = table_start + count * entry_size
    if table_end > file_size:
        raise ValueError("ARC entry table exceeds file")
    table_bytes = read_range(table_start, count * entry_size)
    entries: list[ArcEntry] = []
    for index in range(count):
        offset = table_start + index * entry_size
        table_offset = index * entry_size
        record = table_bytes[table_offset : table_offset + entry_size]
        type_hash, compressed_size, packed_size = struct.unpack_from(
            endian + "III", record, metadata_offset
        )
        payload_offset = struct.unpack_from(endian + "I", record, payload_offset_field)[0]
        payload_end = payload_offset + compressed_size
        if payload_offset > file_size or payload_end > file_size:
            raise ValueError(f"entry {index} payload exceeds file")
        entries.append(
            ArcEntry(
                index=index,
                name=_decode_name(record[:name_bytes]),
                type_hash=type_hash,
                compressed_size=compressed_size,
                raw_size=(packed_size & 0x00FFFFFF) if endian == "<" else packed_size >> 3,
                flags=(packed_size >> 24) if endian == "<" else packed_size & 7,
                packed_size=packed_size,
                payload_offset=payload_offset,
                record=record,
                compressed=b"" if metadata_only else data[payload_offset:payload_end],
            )
        )
    return ArcArchive(
        path,
        data,
        endian,
        data[:4],
        version,
        tuple(entries),
        table_start,
        entry_size,
        name_bytes,
        payload_offset_field,
        platform,
        data_sha,
    )


def _swap_path_segment(path: Path, source: str, target: str) -> Path | None:
    parts = list(path.parts)
    changed = False
    for index, part in enumerate(parts):
        if part.lower() == source.lower():
            parts[index] = target
            changed = True
    return Path(*parts) if changed else None


def _swap_resource_segment(name: str, source: str, target: str) -> str | None:
    parts = name.replace("/", "\\").split("\\")
    changed = False
    for index, part in enumerate(parts):
        if part.lower() == source.lower():
            parts[index] = target
            changed = True
    return "\\".join(parts) if changed else None


def find_jpn_reference(archive_path: Path, resource_name: str) -> tuple[ArcArchive, ArcEntry] | None:
    """Find and load the matching resource from a sibling ``/jpn`` archive."""

    archive_path = Path(archive_path)
    archive_candidates: list[Path] = []
    swapped_archive = _swap_path_segment(archive_path, "eng", "jpn")
    if swapped_archive is not None:
        archive_candidates.append(swapped_archive)
    # Some extracted projects omit the language folder from the archive path.
    # In that case, try a sibling jpn folder while keeping the same relative
    # archive name.
    for parent in archive_path.parents:
        if parent.name.lower() != "eng":
            continue
        archive_candidates.append(parent.parent / "jpn" / archive_path.relative_to(parent))

    names = [resource_name.replace("/", "\\")]
    swapped_resource = _swap_resource_segment(resource_name, "eng", "jpn")
    if swapped_resource is not None:
        names.append(swapped_resource)

    seen: set[Path] = set()
    for candidate_path in archive_candidates:
        candidate_path = candidate_path.resolve()
        if candidate_path in seen or not candidate_path.is_file():
            continue
        seen.add(candidate_path)
        try:
            candidate_archive = parse_arc(candidate_path)
        except Exception:
            continue
        by_name = {entry.name.replace("/", "\\").lower(): entry for entry in candidate_archive.entries}
        for name in names:
            entry = by_name.get(name.lower())
            if entry is not None:
                return candidate_archive, entry
    return None


def unpack_entry(entry: ArcEntry) -> bytes:
    try:
        return zlib.decompress(entry.compressed)
    except zlib.error:
        if entry.compressed_size == entry.raw_size:
            return entry.compressed
        raise


def detect_alignment(archive: ArcArchive) -> int:
    offsets = sorted({entry.payload_offset for entry in archive.entries})
    for alignment in (2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4):
        if offsets and all(offset % alignment == 0 for offset in offsets):
            return alignment
    return 1


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def rebuild_arc(archive: ArcArchive, replacements: dict[int, bytes]) -> bytes:
    """Rebuild an ARC while preserving every untouched compressed payload."""

    if not archive.data:
        raise ValueError("archive was opened as metadata-only; load it fully before writing")
    alignment = detect_alignment(archive)
    first_payload = min(entry.payload_offset for entry in archive.entries)
    table_end = archive.table_start + len(archive.entries) * archive.entry_size
    output = bytearray(archive.data[:first_payload])
    payloads: list[bytes] = []
    raw_sizes: list[int] = []
    for entry in archive.entries:
        if entry.index in replacements:
            raw = replacements[entry.index]
            payloads.append(raw if entry.compressed_size == entry.raw_size else zlib.compress(raw, 9))
            raw_sizes.append(len(raw))
        else:
            payloads.append(entry.compressed)
            raw_sizes.append(entry.raw_size)

    cursor = first_payload
    offsets: list[int] = []
    for payload in payloads:
        cursor = _align(cursor, alignment)
        if len(output) < cursor:
            output.extend(b"\0" * (cursor - len(output)))
        offsets.append(cursor)
        output.extend(payload)
        cursor += len(payload)

    for entry, payload, raw_size, payload_offset in zip(
        archive.entries, payloads, raw_sizes, offsets
    ):
        record_offset = archive.table_start + entry.index * archive.entry_size
        if archive.endian == "<":
            packed_size = (entry.packed_size & 0xFF000000) | raw_size
        else:
            packed_size = (raw_size << 3) | entry.flags
        struct.pack_into(
            archive.endian + "III",
            output,
            record_offset + archive.name_bytes,
            entry.type_hash,
            len(payload),
            packed_size,
        )
        struct.pack_into(
            archive.endian + "I",
            output,
            record_offset + archive.payload_offset_field,
            payload_offset,
        )
    if len(output) < table_end:
        raise AssertionError("rebuilt ARC truncated its entry table")
    return bytes(output)


def is_texture_name(name: str) -> bool:
    lowered = name.lower().replace("/", "\\")
    return (
        lowered.endswith((".xet", ".tex", ".dds", ".png", ".jpg", ".jpeg", ".bmp", ".tga"))
        or "\\texture\\" in lowered
        or "_id_hq" in lowered
    )


def is_message_name(name: str) -> bool:
    lowered = name.lower().replace("/", "\\")
    return lowered.endswith(".msg") or "\\msg\\" in lowered or lowered.startswith("msg\\")


def type_label(type_hash: int, name: str = "") -> str:
    labels = {
        0x241F5DEB: "tex",
        MSG_HASH: "msg",
        FIM_HASH: "mif",
        CSA_HASH: "asc",
        0x1D609FFB: "fnt",
        0x60DD1B16: "lsp",
    }
    if type_hash in labels:
        return labels[type_hash]
    if is_texture_name(name):
        return "texture"
    if is_message_name(name):
        return "msg"
    return "resource"


def xet_info(raw: bytes) -> XetInfo:
    if raw[:4] != b"\0XET":
        raise ValueError("not an XET texture")
    if len(raw) < 20:
        raise ValueError("XET header is truncated")
    # Header layout taken from Kuriimu2's MtTexHeader: bit fields packed
    # LSB-first inside 4-byte blocks read in the stream's byte order, which is
    # big-endian for this "\0XET" PS3 build.
    #   0x04 : version 12 | swizzle 12 | reserved 4 | alphaFlags 4
    #   0x08 : mipCount 6 | width 13 | height 13
    #   0x0C : imgCount 8 | format 8 | unk3 16
    # The old guess at the dimensions agreed only by luck on power-of-two
    # sizes; this reads the real fields, and exposes the swizzle flag that a
    # non-zero value would demand we handle rather than silently misread.
    block4 = struct.unpack_from(">I", raw, 4)[0]
    block8 = struct.unpack_from(">I", raw, 8)[0]
    swizzle = (block4 >> 12) & 0xFFF
    if swizzle:
        raise ValueError(f"XET declares swizzle {swizzle}; de-swizzling is not implemented")
    width = (block8 >> 6) & 0x1FFF
    height = (block8 >> 19) & 0x1FFF
    if width <= 0 or height <= 0:
        raise ValueError("XET has invalid dimensions")
    texture_offset = struct.unpack_from(">I", raw, 16)[0]
    format_code = (struct.unpack_from(">I", raw, 12)[0] >> 8) & 0xFF
    fourcc = XET_FORMATS.get(format_code, "DXT5")
    block_size = 8 if fourcc in ("DXT1", "ATI1") else 16
    payload_size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
    if texture_offset + payload_size > len(raw):
        raise ValueError(
            f"XET payload overruns resource: {width}x{height}, offset=0x{texture_offset:X}"
        )
    return XetInfo(width, height, texture_offset, format_code, fourcc, block_size, payload_size)


def _dds_header(width: int, height: int, payload_size: int, fourcc: str) -> bytes:
    pixel_format = struct.pack("<II4sIIIII", 32, 0x4, fourcc.encode("ascii"), 0, 0, 0, 0, 0)
    return (
        b"DDS "
        + struct.pack("<IIIIIII", 124, 0x000A1007, height, width, payload_size, 0, 1)
        + b"\0" * 44
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )


def decode_xet(raw: bytes) -> tuple[Image.Image, XetInfo]:
    info = xet_info(raw)
    start = info.texture_offset
    end = start + info.payload_size
    dds = _dds_header(info.width, info.height, info.payload_size, info.fourcc) + raw[start:end]
    with Image.open(io.BytesIO(dds)) as decoded:
        image = decoded.convert("RGBA")
        image.load()
        return image, info


def decode_resource(raw: bytes, name: str = "") -> tuple[Image.Image, dict]:
    if raw[:4] == b"\0XET":
        image, info = decode_xet(raw)
        return image, {
            "container": "XET",
            "format": info.fourcc,
            "width": info.width,
            "height": info.height,
            "writable": info.fourcc in WRITABLE_FORMATS,
            "mip_levels": texture_levels(raw, info),
        }
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGBA")
            image.load()
        return image, {
            "container": Path(name).suffix.upper().lstrip(".") or "image",
            "format": "native image",
            "width": image.width,
            "height": image.height,
            "writable": True,
        }
    except Exception as exc:
        raise ValueError(f"unsupported texture/resource format: {exc}") from exc


def decode_csa(csa_raw: bytes | None) -> dict[int, int]:
    """Return TNF-glyph-index -> character-code mappings from a CSA resource."""

    if not csa_raw or csa_raw[:4] != b"\0CSA" or len(csa_raw) < 8:
        return {}
    valid_count = struct.unpack_from(">I", csa_raw, 4)[0]
    count = min(128, max(0, (len(csa_raw) - 8) // 2))
    inverse: dict[int, int] = {}
    for code in range(count):
        glyph_index = struct.unpack_from(">H", csa_raw, 8 + code * 2)[0]
        if glyph_index != 0xFFFF and glyph_index not in inverse:
            inverse[glyph_index] = code
    return inverse


def _decode_gsm_token(token: int, csa_inverse: dict[int, int]) -> str:
    # Control values used by the Utage GSM resources.  They are displayed as
    # readable tags so a translator can preserve them instead of losing them.
    controls = {
        0xFFFF: "<END>",
        0xFFFE: "\\n",
        0xFFFD: "<PAGE_END>",
        0xFFFB: "<PAUSE>",
        0xFED2: "<SPEAKER>",
        0xFC16: "<WINDOW>",
        0xFC17: "<WINDOW_ALT>",
        0xFF92: "<COLOR>",
        0xFF91: "</COLOR>",
        0xFC12: "<CTRL_FC12>",
        0xFC0D: "<CTRL_FC0D>",
        0xFC0F: "<CTRL_FC0F>",
        0xFC11: "<CTRL_FC11>",
    }
    if token in controls:
        return controls[token]
    if token >= 0xF000:
        return f"<CTRL_{token:04X}>"
    if token == 0:
        return " "
    # The ASCII font convention documented by Kuriimu-era Utage tooling uses
    # glyph index + 32 for the printable range.  This is useful even when a
    # matching CSA is not bundled beside a loose .msg file.
    if 1 <= token <= 94:
        return chr(token + 32)
    code = csa_inverse.get(token)
    if code is not None and 32 <= code <= 126:
        return chr(code)
    return f"<GLYPH_{token:04X}>"


def decode_gsm_records(
    raw: bytes,
    *,
    csa_raw: bytes | None = None,
    fim_raw: bytes | None = None,
) -> list[dict]:
    """Decode GSM record boundaries into readable, copyable text."""

    if raw[:4] != b"\0GSM" or len(raw) < 16:
        raise ValueError("not a GSM/.msg resource")
    unit_count, record_count = struct.unpack_from(">II", raw, 8)
    table_start = 16
    units_start = table_start + record_count * 8
    units_end = units_start + unit_count * 2
    if units_end > len(raw):
        raise ValueError("GSM unit table exceeds resource")
    units = struct.unpack_from(">" + str(unit_count) + "H", raw, units_start)
    csa_inverse = decode_csa(csa_raw)
    metrics = decode_fim_metrics(fim_raw, record_count)
    records: list[dict] = []
    for index in range(record_count):
        offset, length = struct.unpack_from(">II", raw, table_start + index * 8)
        if offset > unit_count or offset + length > unit_count:
            raise ValueError(f"GSM record {index} points outside unit table")
        tokens = units[offset : offset + length]
        text_parts: list[str] = []
        for token in tokens:
            text_parts.append(_decode_gsm_token(token, csa_inverse))
        row = {
            "index": index,
            "unit_offset": offset,
            "unit_count": length,
            "text": "".join(text_parts).replace("<END>", ""),
            "tokens": [f"0x{token:04X}" for token in tokens],
        }
        if index < len(metrics):
            row["line_count"] = metrics[index][0]
            row["character_count"] = metrics[index][1]
        records.append(row)
    return records


def decode_fim_metrics(raw: bytes | None, record_count: int) -> list[tuple[int, int]]:
    """Read the useful line/character counts from an optional FIM resource."""

    if not raw or raw[:4] != b"\0FIM" or len(raw) < 32:
        return []
    c1, c2 = struct.unpack_from(">II", raw, 8)
    if c1 != record_count or 32 + c1 * 20 > len(raw):
        return []
    second_start = 32 + c1 * 20
    if second_start + c2 * 44 > len(raw):
        return []
    return [
        struct.unpack_from(">HH", raw, second_start + index * 44) for index in range(min(c2, record_count))
    ]


def format_gsm_document(
    raw: bytes,
    *,
    name: str = "",
    csa_raw: bytes | None = None,
    fim_raw: bytes | None = None,
) -> str:
    records = decode_gsm_records(raw, csa_raw=csa_raw, fim_raw=fim_raw)
    lines = [
        f"Alrummi 3 readable MSG view: {name or '<loose .msg>'}",
        f"GSM records: {len(records)}",
        "Control codes are shown as <TAGS>; preserve them when translating.",
        "",
    ]
    for record in records:
        metrics = ""
        if "line_count" in record:
            metrics = f" · {record['line_count']} line(s), {record['character_count']} chars"
        text = record["text"].replace("\\n", "\n")
        lines.append(f"[{record['index']:04d}] ({record['unit_count']} units{metrics})")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _rgb_to_565(color: tuple[int, int, int]) -> int:
    r, g, b = color
    return ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5) | ((b * 31 + 127) // 255)


def _rgb_from_565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 31
    g = (value >> 5) & 63
    b = value & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def _encode_bc3_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    alphas = [pixel[3] for pixel in pixels]
    alpha0, alpha1 = max(alphas), min(alphas)
    alpha_palette = (
        [alpha0] * 8
        if alpha0 == alpha1
        else [
            alpha0,
            alpha1,
            (6 * alpha0 + alpha1 + 3) // 7,
            (5 * alpha0 + 2 * alpha1 + 3) // 7,
            (4 * alpha0 + 3 * alpha1 + 3) // 7,
            (3 * alpha0 + 4 * alpha1 + 3) // 7,
            (2 * alpha0 + 5 * alpha1 + 3) // 7,
            (alpha0 + 6 * alpha1 + 3) // 7,
        ]
    )
    alpha_bits = 0
    for index, alpha in enumerate(alphas):
        choice = min(range(8), key=lambda item: abs(alpha - alpha_palette[item]))
        alpha_bits |= choice << (index * 3)

    visible = [pixel[:3] for pixel in pixels if pixel[3] >= 16] or [(0, 0, 0)]
    darkest = min(visible, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
    brightest = max(visible, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
    color0, color1 = _rgb_to_565(brightest), _rgb_to_565(darkest)
    if color0 <= color1:
        if color1 < 0xFFFF:
            color0 = color1 + 1
        elif color0 > 0:
            color1 = color0 - 1
    c0, c1 = _rgb_from_565(color0), _rgb_from_565(color1)
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
    return bytes((alpha0, alpha1)) + alpha_bits.to_bytes(6, "little") + struct.pack(
        "<HHI", color0, color1, color_bits
    )


def mip_chain(width: int, height: int, block_size: int) -> list[tuple[int, int, int]]:
    """Every mip level as (width, height, byte size), largest first."""

    levels = []
    w, h = width, height
    while True:
        size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block_size
        levels.append((w, h, size))
        if w == 1 and h == 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
    return levels


def texture_levels(raw: bytes, info: "XetInfo") -> int:
    """How many mip levels this resource actually stores."""

    available = len(raw) - info.texture_offset
    used = 0
    for index, (_w, _h, size) in enumerate(mip_chain(info.width, info.height, info.block_size)):
        if used + size > available:
            return max(1, index)
        used += size
        if used == available:
            return index + 1
    return 1


def patch_texture_rect(
    raw: bytes,
    image: Image.Image,
    region: Region,
    *,
    rebuild_mips: bool = True,
) -> bytes:
    """Re-encode the blocks a region touches, leaving every other block alone.

    The whole candidate is encoded once with the block encoder in `bcn`, then
    only the blocks inside the region are copied over the original.  That keeps
    untouched blocks byte-identical while still using a proper endpoint fit for
    the ones that change.

    Lower mip levels are regenerated from the candidate when the resource
    stores them, because a texture whose top level is English and whose mips
    are still Japanese reverts at distance.
    """

    info = xet_info(raw)
    if info.fourcc not in ("DXT1", "DXT5"):
        raise ValueError(f"no encoder for {info.fourcc} textures")
    if image.size != (info.width, info.height):
        raise ValueError(
            f"candidate size {image.size} does not match XET size {(info.width, info.height)}"
        )

    rgba = image.convert("RGBA")
    encoded = bcn.encode(np.asarray(rgba, dtype=np.uint8), info.fourcc)
    block_bytes = info.block_size
    blocks_w = max(1, (info.width + 3) // 4)

    box = region.clipped(rgba.size)
    left = box.left // 4
    top = box.top // 4
    right = min(blocks_w, (box.right + 3) // 4)
    bottom = min(max(1, (info.height + 3) // 4), (box.bottom + 3) // 4)

    output = bytearray(raw)
    for block_y in range(top, bottom):
        first = (block_y * blocks_w + left) * block_bytes
        span = max(0, right - left) * block_bytes
        if span <= 0:
            continue
        destination = info.texture_offset + first
        output[destination : destination + span] = encoded[first : first + span]

    levels = texture_levels(raw, info)
    if rebuild_mips and levels > 1:
        chain = mip_chain(info.width, info.height, block_bytes)
        offset = info.texture_offset + chain[0][2]
        for width, height, size in chain[1:levels]:
            level = rgba.resize((width, height), Image.Resampling.LANCZOS)
            blob = bcn.encode(np.asarray(level, dtype=np.uint8), info.fourcc)
            output[offset : offset + size] = blob[:size]
            offset += size

    return bytes(output)


# Kept under the old name so existing callers keep working.
def patch_bc3_rect(raw: bytes, image: Image.Image, region: Region) -> bytes:
    return patch_texture_rect(raw, image, region)


SERIF_ITALIC_FONTS = ("georgiaz.ttf", "timesbi.ttf", "cambriaz.ttf", "palabi.ttf")
SANS_BOLD_FONTS = ("arialbd.ttf", "segoeuib.ttf", "timesbi.ttf")


def choose_font(requested: str | None = None, style: str = "sans") -> Path | None:
    """Pick a font file, preferring a bold italic serif for game lettering.

    The Utage and Samurai Heroes nameplates are set in a bold italic serif.
    Rendering a replacement in Arial Bold is what makes a generated texture
    read as obviously wrong beside the real ones.
    """

    names = SERIF_ITALIC_FONTS if style == "serif_italic" else SANS_BOLD_FONTS
    candidates = [Path(requested)] if requested else []
    candidates += [Path(r"C:\Windows\Fonts") / name for name in names]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Wrap text by rendered pixel width, including long unbroken strings."""

    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            proposed = word if not current else f"{current} {word}"
            if draw.textlength(proposed, font=font) <= max_width:
                current = proposed
                continue
            if current:
                lines.append(current)
            current = ""
            for character in word:
                proposed = current + character
                if current and draw.textlength(proposed, font=font) > max_width:
                    lines.append(current)
                    current = character
                else:
                    current = proposed
        if current:
            lines.append(current)
    return lines or [""]


def _fit_text_layout(
    draw: ImageDraw.ImageDraw,
    text: str,
    region: Region,
    font_path: Path | None,
    width_ratio: float = 0.86,
    prefer_single_line: bool = False,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    if font_path is None:
        font = ImageFont.load_default()
        lines = _wrap_text(draw, text, font, max(1, round(region.width * width_ratio)))
        return font, lines, 1
    # Start from a size that fills the box and step down until the wrapped
    # text fits.  Capping at 30% of the height made single-line nameplates
    # render tiny even when the whole texture was theirs to use.
    maximum = max(8, min(256, round(region.height * 0.80)))
    minimum = 7
    max_width = max(1, round(region.width * width_ratio))
    max_height = max(1, round(region.height * 0.84))
    def measure(size: int) -> tuple[ImageFont.ImageFont, list[str], int, int]:
        font = ImageFont.truetype(str(font_path), size)
        lines = _wrap_text(draw, text, font, max_width)
        bbox = font.getbbox("Ag")
        line_height = max(1, bbox[3] - bbox[1])
        spacing = max(1, round(size * 0.16))
        total = line_height * len(lines) + spacing * max(0, len(lines) - 1)
        return font, lines, spacing, total

    words = text.split()

    def breaks_a_word(font) -> bool:
        # A size that cannot fit the longest single word will hyphenate it into
        # nonsense like "Fortu / ne", so it is rejected in favour of a smaller
        # one that keeps words whole.
        return any(draw.textlength(word, font=font) > max_width for word in words)

    if prefer_single_line:
        # Take the largest size that still keeps the whole string on one line.
        for size in range(maximum, minimum - 1, -1):
            font, lines, spacing, total = measure(size)
            if len(lines) == 1 and total <= max_height:
                return font, lines, spacing

    for size in range(maximum, minimum - 1, -1):
        font, lines, spacing, total = measure(size)
        if total <= max_height and not breaks_a_word(font):
            return font, lines, spacing

    # Nothing kept every word whole; fall back to the best that simply fits.
    for size in range(maximum, minimum - 1, -1):
        font, lines, spacing, total = measure(size)
        if total <= max_height:
            return font, lines, spacing
    font = ImageFont.truetype(str(font_path), minimum)
    return font, _wrap_text(draw, text, font, max_width), 1


def sample_ink_color(image: Image.Image, region: Region) -> tuple[int, int, int, int] | None:
    """Read the colour of the lettering that is already there.

    Replacement text rendered in a default cream reads as foreign next to the
    game's own green glyphs.  Sampling the existing ink keeps a generated
    texture in the palette the artwork already uses.
    """

    crop = image.crop((region.left, region.top, region.right, region.bottom)).convert("RGBA")
    try:
        pixels = list(crop.get_flattened_data())
    except AttributeError:
        pixels = list(crop.getdata())
    solid = [p for p in pixels if p[3] > 160]
    if len(solid) < 8:
        return None
    # Glyph cores are the brightest solid pixels; edges are antialiased toward
    # the background and would drag the average toward grey.
    solid.sort(key=lambda p: p[0] + p[1] + p[2], reverse=True)
    core_pixels = solid[: max(8, len(solid) // 5)]
    count = len(core_pixels)
    return (
        sum(p[0] for p in core_pixels) // count,
        sum(p[1] for p in core_pixels) // count,
        sum(p[2] for p in core_pixels) // count,
        255,
    )


def _erase_region(image: Image.Image, region: Region) -> str:
    """Remove existing lettering from a region as cleanly as the art allows.

    A nameplate is transparent with glyphs floating on it, so a blur only
    smears the old glyphs into a visible ghost.  When the region's border is
    transparent the honest clear is to erase to that same transparent colour;
    only lettering baked onto opaque art needs the blur.
    """

    crop = image.crop((region.left, region.top, region.right, region.bottom))
    alpha = crop.getchannel("A")
    width, height = crop.size
    border: list[int] = []
    for x in range(width):
        border.append(alpha.getpixel((x, 0)))
        border.append(alpha.getpixel((x, height - 1)))
    for y in range(height):
        border.append(alpha.getpixel((0, y)))
        border.append(alpha.getpixel((width - 1, y)))
    border.sort()
    median_alpha = border[len(border) // 2] if border else 255

    if median_alpha < 32:
        # Keep the RGB the art already uses under transparent pixels so the
        # replacement matches the game's own convention.
        backdrop = crop.getpixel((0, 0))
        fill = (backdrop[0], backdrop[1], backdrop[2], 0)
        image.paste(Image.new("RGBA", crop.size, fill), (region.left, region.top))
        return "erased_to_transparent"

    blur_radius = max(1, min(8, round(min(region.width, region.height) / 28)))
    image.paste(crop.filter(ImageFilter.GaussianBlur(blur_radius)), (region.left, region.top))
    return "blurred"


def _polish_texture(source: Image.Image) -> Image.Image:
    """Make a restrained visual copy while preserving the original dimensions."""

    image = source.convert("RGBA")
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.018)
    rgb = ImageEnhance.Color(rgb).enhance(1.015)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.06)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=28, threshold=4))
    polished = rgb.convert("RGBA")
    polished.putalpha(alpha)
    return polished


def generate_visual_copy(
    source: Image.Image,
    english_text: str = "",
    region: Region | None = None,
    *,
    font_path: str | None = None,
    color: tuple[int, int, int, int] = (248, 255, 238, 255),
    clear_existing: bool = False,
    polish: bool = True,
    auto_color: bool = True,
) -> tuple[Image.Image, dict]:
    """Create a polished, same-size texture copy using the source as its base."""

    image = _polish_texture(source) if polish else source.convert("RGBA").copy()
    region = (region or Region(0, 0, image.width, image.height)).clipped(image.size)
    full_texture = region.as_list() == [0, 0, image.width, image.height]
    text_region = region
    # A wide, short texture is a nameplate or banner: the lettering is the
    # whole point of it, so it gets the whole canvas rather than a title band.
    banner = image.width >= image.height * 2.5
    if full_texture and not clear_existing and not banner:
        # A full-canvas selection is the default canvas, not a request to put
        # a poster-sized paragraph over the whole image.  Use the upper band
        # as a title area so the source artwork remains the visual anchor.
        text_region = Region(
            round(image.width * 0.06),
            round(image.height * 0.035),
            round(image.width * 0.94),
            round(image.height * 0.245),
        ).clipped(image.size)
    text = " ".join(english_text.split())
    rendered_lines: list[str] = []
    cleared = False
    # Sample before anything is erased, or there is nothing left to sample.
    sampled_color = sample_ink_color(image, text_region) if auto_color else None
    if sampled_color is not None:
        color = sampled_color
    clear_method = ""
    if clear_existing:
        # Clearing applies to a full-texture selection too.  Skipping it there
        # left the Japanese visible underneath the English, which is exactly
        # what made a replaced nameplate look like a mistake.
        clear_method = _erase_region(image, region)
        cleared = True
        # The cleared box is now the working area, so use all of it.
        text_region = region

    if text:
        draw = ImageDraw.Draw(image)
        font_file = choose_font(font_path, "serif_italic" if banner else "sans")
        font, lines, spacing = _fit_text_layout(
            draw,
            text,
            text_region,
            font_file,
            0.94 if banner else 0.86,
            prefer_single_line=banner,
        )
        rendered_lines = list(lines)
        bbox = font.getbbox("Ag")
        line_height = max(1, bbox[3] - bbox[1])
        total_height = line_height * len(lines) + spacing * max(0, len(lines) - 1)
        y = text_region.top + max(0, (text_region.height - total_height) // 2) - bbox[1]
        panel_margin = max(6, round(min(text_region.width, text_region.height) * 0.08))
        # The backing plate exists to keep text legible over busy artwork.  On
        # a cleared box or a nameplate it is just a dark rectangle in the way.
        if text_region.width > panel_margin * 4 and not cleared and not banner:
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(
                (
                    text_region.left + panel_margin,
                    text_region.top + panel_margin,
                    text_region.right - panel_margin,
                    text_region.bottom - panel_margin,
                ),
                radius=max(4, panel_margin),
                fill=(7, 18, 13, 112 if full_texture else 92),
                outline=(203, 255, 210, 130),
                width=max(1, panel_margin // 3),
            )
            image = Image.alpha_composite(image, overlay)
            draw = ImageDraw.Draw(image)
        shadow = (0, 18, 8, min(230, color[3]))
        stroke = (5, 18, 10, min(220, color[3]))
        for line in lines:
            line_box = draw.textbbox((0, 0), line, font=font, stroke_width=0)
            line_width = line_box[2] - line_box[0]
            x = text_region.left + max(0, (text_region.width - line_width) // 2) - line_box[0]
            draw.text((x + 2, y + 3), line, font=font, fill=shadow, stroke_width=max(1, round(getattr(font, "size", 10) * 0.06)), stroke_fill=stroke)
            draw.text((x, y), line, font=font, fill=color, stroke_width=max(1, round(getattr(font, "size", 10) * 0.02)), stroke_fill=stroke)
            y += line_height + spacing

    return image, {
        "mode": "polished_visual_copy",
        "text": text,
        "lines": rendered_lines if text else [],
        "region": region.as_list(),
        "text_region": text_region.as_list(),
        "font": str(choose_font(font_path, "serif_italic" if banner else "sans") or "Pillow default"),
        "font_size": getattr(font, "size", None) if text else None,
        "clear_existing": clear_existing,
        "cleared_region": cleared,
        "clear_method": clear_method,
        "banner_layout": banner,
        "polish": polish,
        "source_dimensions": list(source.size),
        "candidate_dimensions": list(image.size),
        "dimensions_match": image.size == source.size,
        "color": list(color),
        "color_sampled_from_source": sampled_color is not None,
    }


def generate_candidate(
    source: Image.Image,
    english_text: str,
    region: Region,
    *,
    font_path: str | None = None,
    color: tuple[int, int, int, int] = (123, 255, 123, 255),
    clear_existing: bool = True,
) -> tuple[Image.Image, dict]:
    """Render a reviewable English candidate without touching an archive."""
    text = " ".join(english_text.split())
    if not text:
        raise ValueError("enter English text before generating a candidate")
    return generate_visual_copy(
        source,
        text,
        region,
        font_path=font_path,
        color=color,
        clear_existing=clear_existing,
        polish=False,
    )


def swap_xet_payload(source_raw: bytes, donor_raw: bytes) -> bytes:
    """Replace a texture's block payload with a donor's, byte for byte.

    Re-encoding a donor through the BC3 encoder visibly softens lettering that
    was already compressed once.  When the donor has identical dimensions and
    format there is no reason to re-encode at all: the compressed blocks can be
    copied straight across, keeping the source header and everything after the
    payload untouched.
    """

    source = xet_info(source_raw)
    donor = xet_info(donor_raw)
    if (source.width, source.height, source.fourcc, source.payload_size) != (
        donor.width,
        donor.height,
        donor.fourcc,
        donor.payload_size,
    ):
        raise ValueError(
            f"donor {donor.width}x{donor.height} {donor.fourcc} does not match "
            f"source {source.width}x{source.height} {source.fourcc}"
        )
    # Textures in this game may carry mipmaps after the top level.  Copying
    # only the top mip leaves the source's smaller levels in place, so the
    # Japanese would still appear at distance.  When both resources are the
    # same length with the same payload start, copy everything from the
    # payload onward so every mip level comes from the donor.
    if len(donor_raw) == len(source_raw) and donor.texture_offset == source.texture_offset:
        return source_raw[: source.texture_offset] + donor_raw[donor.texture_offset :]

    payload = donor_raw[donor.texture_offset : donor.texture_offset + donor.payload_size]
    if len(payload) != source.payload_size:
        raise ValueError("donor payload is truncated")
    tail_source = len(source_raw) - (source.texture_offset + source.payload_size)
    if tail_source:
        raise ValueError(
            f"source carries {tail_source} bytes after the top mip level and the "
            "donor is a different length, so lower mips cannot be replaced safely"
        )
    return source_raw[: source.texture_offset] + payload


def patch_region_from(
    base: Image.Image,
    donor: Image.Image,
    region: Region,
    *,
    feather: int = 0,
) -> Image.Image:
    """Copy one rectangle of a donor into a base image.

    This is the surgical repair: when only one word or one corner of a texture
    is wrong, take just that rectangle from the official English texture and
    leave every other pixel untouched.  Both images must be the same size, so
    the rectangle lands exactly where it came from.
    """

    if donor.size != base.size:
        raise ValueError(
            f"donor is {donor.width}x{donor.height} but the texture is "
            f"{base.width}x{base.height}; fit the donor first"
        )
    out = base.convert("RGBA").copy()
    box = region.clipped(out.size)
    crop = donor.convert("RGBA").crop((box.left, box.top, box.right, box.bottom))
    if feather > 0:
        mask = Image.new("L", crop.size, 255)
        draw = ImageDraw.Draw(mask)
        for step in range(feather):
            value = int(255 * (step + 1) / (feather + 1))
            draw.rectangle((step, step, crop.width - 1 - step, crop.height - 1 - step),
                           outline=value)
        out.paste(crop, (box.left, box.top), mask)
    else:
        out.paste(crop, (box.left, box.top))
    return out


def erase_region(base: Image.Image, region: Region) -> tuple[Image.Image, str]:
    """Clear one rectangle the way the artwork itself is cleared."""

    out = base.convert("RGBA").copy()
    method = _erase_region(out, region.clipped(out.size))
    return out, method


def render_text_in_region(
    base: Image.Image,
    text: str,
    region: Region,
    *,
    font_path: str | None = None,
    clear_first: bool = True,
    auto_color: bool = True,
) -> tuple[Image.Image, dict]:
    """Draw text into one rectangle only, leaving the rest of the texture alone."""

    out = base.convert("RGBA").copy()
    box = region.clipped(out.size)
    banner = box.width >= box.height * 2.5
    color = (248, 255, 238, 255)
    sampled = sample_ink_color(out, box) if auto_color else None
    if sampled is not None:
        color = sampled
    method = ""
    if clear_first:
        method = _erase_region(out, box)
    words = " ".join(text.split())
    lines: list[str] = []
    if words:
        draw = ImageDraw.Draw(out)
        font_file = choose_font(font_path, "serif_italic" if banner else "sans")
        font, lines, spacing = _fit_text_layout(
            draw, words, box, font_file, 0.94 if banner else 0.86,
            prefer_single_line=banner,
        )
        bbox = font.getbbox("Ag")
        line_height = max(1, bbox[3] - bbox[1])
        total = line_height * len(lines) + spacing * max(0, len(lines) - 1)
        y = box.top + max(0, (box.height - total) // 2) - bbox[1]
        stroke = (5, 18, 10, min(220, color[3]))
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=font, stroke_width=0)
            x = box.left + max(0, (box.width - (lb[2] - lb[0])) // 2) - lb[0]
            draw.text((x, y), line, font=font, fill=color,
                      stroke_width=max(1, round(getattr(font, "size", 10) * 0.02)),
                      stroke_fill=stroke)
            y += line_height + spacing
    return out, {
        "mode": "region_text",
        "region": box.as_list(),
        "text": words,
        "lines": lines,
        "clear_method": method,
        "color": list(color),
        "color_sampled_from_source": sampled is not None,
        "banner_layout": banner,
    }


def encode_replacement(raw: bytes, name: str, candidate: Image.Image, region: Region) -> bytes:
    if raw[:4] == b"\0XET":
        return patch_bc3_rect(raw, candidate, region)
    suffix = Path(name).suffix.lower()
    output = io.BytesIO()
    format_name = {".jpg": "JPEG", ".jpeg": "JPEG", ".bmp": "BMP", ".tga": "TGA"}.get(
        suffix, "PNG"
    )
    to_save = candidate.convert("RGB") if format_name == "JPEG" else candidate
    to_save.save(output, format=format_name)
    return output.getvalue()


def entry_report(entry: ArcEntry, raw: bytes | None = None) -> dict:
    return {
        "index": entry.index,
        "name": entry.name,
        "type_hash": f"0x{entry.type_hash:08X}",
        "compressed_size": entry.compressed_size,
        "raw_size_declared": entry.raw_size,
        "raw_size_actual": len(raw) if raw is not None else None,
        "flags": entry.flags,
        "payload_offset": entry.payload_offset,
        "raw_sha256": sha256(raw) if raw is not None else None,
    }


def verify_single_replacement(before: ArcArchive, after: ArcArchive, index: int) -> dict:
    if len(before.entries) != len(after.entries):
        raise AssertionError("entry count changed")
    changed: list[int] = []
    for old, new in zip(before.entries, after.entries):
        if unpack_entry(old) != unpack_entry(new):
            changed.append(old.index)
        if old.name != new.name or old.type_hash != new.type_hash or old.flags != new.flags:
            raise AssertionError(f"archive metadata changed for entry {old.index}")
    if changed != [index]:
        raise AssertionError(f"expected only entry {index} to change, got {changed}")
    return {
        "status": "pass",
        "changed_entries": changed,
        "entry_count": len(after.entries),
        "input_sha256": sha256(before.data),
        "output_sha256": sha256(after.data),
    }


def write_audit(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
