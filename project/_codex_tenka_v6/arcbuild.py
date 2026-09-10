"""Rebuild an MT Framework ARC v8 from a chosen subset of a source archive's
entries, with per-entry payload replacement.  Entry records (name, flags) are
carried over verbatim; only sizes and offsets are recomputed."""
from __future__ import annotations
import struct, zlib
from pathlib import Path
import sys
sys.path.insert(0, r"E:\Utage Patching New\_codex_tenka_v6")
import arc_tools as A

ENTRY_SIZE = 80
TABLE_START = 8


def build(arc: "A.Archive", keep: list[int], replacements: dict[int, bytes]) -> bytes:
    """keep: source entry indices, in output order.  replacements: index -> raw bytes."""
    alignment = A.detect_alignment(arc)
    count = len(keep)
    payloads, raw_sizes = [], []
    for idx in keep:
        e = arc.entries[idx]
        if idx in replacements:
            raw = replacements[idx]
            stored_plain = e.compressed_size == e.raw_size
            payloads.append(raw if stored_plain else zlib.compress(raw, 9))
            raw_sizes.append(len(raw))
        else:
            payloads.append(e.compressed)
            raw_sizes.append(e.raw_size)

    table_end = TABLE_START + count * ENTRY_SIZE
    first_payload = A.align(table_end, alignment)
    out = bytearray(first_payload)
    out[0:4] = arc.magic
    struct.pack_into(arc.endian + "HH", out, 4, arc.version, count)

    cursor = first_payload
    for slot, (idx, payload, raw_size) in enumerate(zip(keep, payloads, raw_sizes)):
        cursor = A.align(cursor, alignment)
        if len(out) < cursor:
            out.extend(b"\0" * (cursor - len(out)))
        rec = arc.entries[idx].record
        off = TABLE_START + slot * ENTRY_SIZE
        out[off:off + 64] = rec[:64]
        struct.pack_into(
            arc.endian + "IIII", out, off + 64,
            arc.entries[idx].type_hash, len(payload),
            (raw_size << 3) | arc.entries[idx].flags, cursor,
        )
        out.extend(payload)
        cursor += len(payload)
    return bytes(out)
