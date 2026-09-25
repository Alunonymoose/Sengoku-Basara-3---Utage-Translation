"""Conservative PS3 ARC v8 byte-preserving rebuild primitives (Python 3.10+).

Port/adaptation of Foundry UtageArcReader/UtageArcWriter at
bd0f8544f7090040a0e9613c08a75377631be3b1, under
project/Foundry/src/BasaraFoundry.Game.Utage/Arc/ in
Alunonymoose/Sengoku-Basara-3---Utage-Translation.

Additional production guards: complete zlib-stream validation independent of
size equality, overlaps and nonzero gaps/trailers rejected, original physical
order retained, effective no-ops are exact bytes, all untouched stored bytes
and packed-size fields retained. Real Utage has complete valid zlib streams
whose decoded length differs from packed_size >> 3 (e.g. cockpit1P dummy_BM).
These are explicit warnings, not guessed alternate codecs. Their original
packed field is preserved and replacements must retain actual decoded size.

No filesystem writes, texture encoding, install operation or runtime claims.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Mapping

SOURCE_COMMIT = "bd0f8544f7090040a0e9613c08a75377631be3b1"
ENTRY_SIZE = 80
ALIGNMENTS = (2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(stored: bytes, declared: int, index: int) -> tuple[bytes, str, str | None]:
    # Require a valid RFC1950 header before attempting zlib. If advertised as
    # zlib, truncated/trailing/malformed data must not fall back to plain data.
    zlib_header = (len(stored) >= 2 and stored[0] & 15 == 8
                   and stored[0] >> 4 <= 7
                   and ((stored[0] << 8) | stored[1]) % 31 == 0)
    if zlib_header:
        dec = zlib.decompressobj()
        try:
            raw = dec.decompress(stored) + dec.flush()
        except zlib.error as exc:
            raise ValueError(f"member {index}: invalid zlib stream: {exc}") from exc
        if not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise ValueError(f"member {index}: incomplete or trailing zlib stream")
        warning = (f"declared_raw_size:{declared}!=decoded_size:{len(raw)}"
                   if len(raw) != declared else None)
        return raw, "zlib", warning
    if len(stored) == declared:
        return stored, "raw", None
    raise ValueError(f"member {index}: unsupported non-zlib unequal-size storage "
                     f"({len(stored)} stored, {declared} declared)")


def inspect_arc(data: bytes) -> tuple[list[dict], list[dict]]:
    """Parse ARC members while reporting non-zero container padding/trailers.

    This is intended for read-only corpus indexing/forensics. It keeps all
    header, range, codec and overlap validation strict, but reports non-zero
    bytes between otherwise valid payload regions (or after the final payload)
    as container anomalies instead of discarding the entire archive.

    Production mutation must continue to use parse_arc(), which rejects these
    anomalies fail-closed.
    """
    if not isinstance(data, bytes):
        raise TypeError("ARC input must be immutable bytes")
    if len(data) < 8 or data[:4] != b"\0CRA":
        raise ValueError("expected PS3 big-endian ARC header")
    version, count = struct.unpack_from(">HH", data, 4)
    if version != 8:
        raise ValueError(f"unsupported ARC version: {version}")
    table_end = 8 + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError("ARC entry table exceeds source")
    entries = []
    for index in range(count):
        start = 8 + index * ENTRY_SIZE
        record = data[start:start + ENTRY_SIZE]
        type_hash, size, packed, offset = struct.unpack_from(">IIII", record, 64)
        if offset < table_end or offset + size > len(data):
            raise ValueError(f"member {index}: payload range outside ARC")
        name = record[:64].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        stored = data[offset:offset + size]
        raw, codec, warning = _decode(stored, packed >> 3, index)
        entries.append(dict(index=index, name=name, type_hash=type_hash,
                            compressed_size=size, raw_size=packed >> 3,
                            flags=packed & 7, packed_size=packed,
                            payload_offset=offset, record=record, stored=stored,
                            raw=raw, codec=codec, warning=warning))
    anomalies = []
    cursor = table_end
    for entry in sorted(entries, key=lambda e: (e["payload_offset"], e["index"])):
        offset = entry["payload_offset"]
        if offset < cursor:
            raise ValueError(f"member {entry['index']}: overlapping payloads")
        gap = data[cursor:offset]
        if any(gap):
            anomalies.append(dict(kind="nonzero_gap", start=cursor, end=offset,
                                  size=len(gap), sha256=sha256(gap)))
        cursor = offset + entry["compressed_size"]
    trailer = data[cursor:]
    if any(trailer):
        anomalies.append(dict(kind="nonzero_trailer", start=cursor, end=len(data),
                              size=len(trailer), sha256=sha256(trailer)))
    return entries, anomalies


def parse_arc(data: bytes) -> list[dict]:
    """Validate a complete mutation-safe ARC and return logical entries."""
    entries, anomalies = inspect_arc(data)
    if anomalies:
        first = anomalies[0]
        if first["kind"] == "nonzero_gap":
            raise ValueError(f"nonzero ARC gap: {first['start']:#x}..{first['end']:#x}")
        raise ValueError(f"nonzero ARC trailer at {first['start']:#x}")
    return entries


def detect_alignment(entries: list[dict]) -> int:
    if not entries:
        return 1
    for alignment in ALIGNMENTS:
        if all(e["payload_offset"] % alignment == 0 for e in entries):
            return alignment
    return 1


def _replacement_map(entries: list[dict], replacements: Mapping[int, bytes]) -> dict[int, bytes]:
    effective = {}
    for index, raw in replacements.items():
        if type(index) is not int or index < 0 or index >= len(entries):
            raise ValueError(f"unknown replacement index: {index!r}")
        if not isinstance(raw, bytes):
            raise TypeError(f"replacement {index} must be immutable bytes")
        if len(raw) > 0x1FFFFFFF:
            raise ValueError(f"replacement {index} exceeds packed-size range")
        entry = entries[index]
        if entry["warning"] and len(raw) != len(entry["raw"]):
            raise ValueError(f"member {index}: declared-size mismatch prohibits "
                             "changing actual decoded length")
        if raw != entry["raw"]:
            effective[index] = raw
    return effective


def rebuild_arc(data: bytes, replacements: Mapping[int, bytes]) -> bytes:
    """Rebuild exact source bytes; preserve untouched stored payloads verbatim."""
    entries = parse_arc(data)
    replacements = _replacement_map(entries, replacements)
    if not replacements:
        return data
    ordered = sorted(entries, key=lambda e: (e["payload_offset"], e["index"]))
    alignment = detect_alignment(entries)
    out = bytearray(data[:ordered[0]["payload_offset"]])
    for entry in ordered:
        index = entry["index"]
        raw = replacements.get(index)
        if raw is None:
            stored, packed = entry["stored"], entry["packed_size"]
        else:
            stored = zlib.compress(raw, 9) if entry["codec"] == "zlib" else raw
            # Even misleading packed fields are identity metadata unless the
            # replacement intentionally changes an ordinary member's length.
            packed = (entry["packed_size"] if len(raw) == len(entry["raw"])
                      else (len(raw) << 3) | entry["flags"])
        offset = ((len(out) + alignment - 1) // alignment) * alignment
        out.extend(b"\0" * (offset - len(out)))
        out.extend(stored)
        struct.pack_into(">III", out, 8 + index * ENTRY_SIZE + 68,
                         len(stored), packed, offset)
    old_end = max(e["payload_offset"] + e["compressed_size"] for e in entries)
    out.extend(data[old_end:])  # preserve verified zero trailer length
    result = bytes(out)
    verify_rebuild(data, result, replacements)
    return result


def verify_rebuild(source: bytes, output: bytes,
                   replacements: Mapping[int, bytes]) -> dict:
    """Reparse/extract both archives and verify complete preservation contract."""
    before, after = parse_arc(source), parse_arc(output)
    effective = _replacement_map(before, replacements)
    if source[:8] != output[:8] or len(before) != len(after):
        raise ValueError("ARC header/version/count changed")
    if not effective and source != output:
        raise ValueError("effective no-op changed archive bytes")
    changed = []
    for old, new in zip(before, after):
        index = old["index"]
        if old["record"][:68] != new["record"][:68] or old["flags"] != new["flags"]:
            raise ValueError(f"member {index}: protected metadata changed")
        expected = effective.get(index)
        if expected is None:
            if old["record"][68:76] != new["record"][68:76] or old["stored"] != new["stored"]:
                raise ValueError(f"untouched member {index}: stored bytes/size changed")
        else:
            if new["raw"] != expected or new["codec"] != old["codec"]:
                raise ValueError(f"member {index}: replacement did not round-trip")
            expected_packed = (old["packed_size"] if len(expected) == len(old["raw"])
                               else (len(expected) << 3) | old["flags"])
            if new["packed_size"] != expected_packed:
                raise ValueError(f"member {index}: packed-size contract changed")
            changed.append(dict(index=index, name=old["name"],
                                before_raw_sha256=sha256(old["raw"]),
                                after_raw_sha256=sha256(new["raw"]),
                                before_stored_sha256=sha256(old["stored"]),
                                after_stored_sha256=sha256(new["stored"])))
    before_order = [e["index"] for e in sorted(before, key=lambda e: (e["payload_offset"], e["index"]))]
    after_order = [e["index"] for e in sorted(after, key=lambda e: (e["payload_offset"], e["index"]))]
    if before_order != after_order:
        raise ValueError("physical payload ordering changed")
    alignment = detect_alignment(before)
    if any(e["payload_offset"] % alignment for e in after):
        raise ValueError("payload alignment changed")
    return dict(source_sha256=sha256(source), output_sha256=sha256(output),
                member_count=len(before), changed_member_count=len(changed),
                untouched_stored_verified=len(before) - len(changed),
                alignment=alignment, changes=changed,
                warnings=[dict(index=e["index"], name=e["name"], warning=e["warning"])
                          for e in before if e["warning"]])