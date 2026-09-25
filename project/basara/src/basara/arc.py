"""MT Framework ARC v8 (PS3, big-endian ``\\0CRA``) -- read, rebuild, verify.

Semantics are identical to the pinned ``safe_arc.py`` (7beb24a5...f6f3); the
test-suite proves it with a differential property test. What changes:

* typed, immutable models instead of dicts;
* **lazy inflation** -- listing an archive, hashing stored bytes or finding a
  member never decompresses anything (safe_arc inflates every member on
  parse; indexing 11k live ARCs is dominated by that cost);
* ``inspect()`` reads the eight "special" live ARCs (non-zero gaps/trailers)
  read-only, with the anomalies reported instead of raised;
* lookups by index, exact name, name suffix, magic and type hash.

Mutation stays fail-closed: ``rebuild()`` only accepts archives that pass the
strict ``read()`` contract.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable, Iterator, Mapping, Optional

MAGIC = b"\x00CRA"
VERSION = 8
ENTRY_SIZE = 80
TABLE_START = 8
ALIGNMENTS = (2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4)


class ArcError(ValueError):
    """Malformed archive or refused mutation."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _has_zlib_header(stored: bytes) -> bool:
    return (len(stored) >= 2 and stored[0] & 15 == 8 and stored[0] >> 4 <= 7
            and ((stored[0] << 8) | stored[1]) % 31 == 0)


def _inflate(stored: bytes, declared: int, index: int) -> tuple[bytes, str, Optional[str]]:
    if _has_zlib_header(stored):
        dec = zlib.decompressobj()
        try:
            raw = dec.decompress(stored) + dec.flush()
        except zlib.error as exc:
            raise ArcError(f"member {index}: invalid zlib stream: {exc}") from exc
        if not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise ArcError(f"member {index}: incomplete or trailing zlib stream")
        warning = (f"declared_raw_size:{declared}!=decoded_size:{len(raw)}"
                   if len(raw) != declared else None)
        return raw, "zlib", warning
    if len(stored) == declared:
        return stored, "raw", None
    raise ArcError(f"member {index}: unsupported non-zlib unequal-size storage "
                   f"({len(stored)} stored, {declared} declared)")


@dataclass(frozen=True)
class Entry:
    index: int
    name: str
    type_hash: int
    compressed_size: int
    packed_size: int
    payload_offset: int
    record: bytes
    stored: bytes

    @property
    def raw_size(self) -> int:
        return self.packed_size >> 3

    @property
    def flags(self) -> int:
        return self.packed_size & 7

    @cached_property
    def _decoded(self) -> tuple[bytes, str, Optional[str]]:
        return _inflate(self.stored, self.raw_size, self.index)

    @property
    def raw(self) -> bytes:
        return self._decoded[0]

    @property
    def codec(self) -> str:
        return self._decoded[1]

    @property
    def warning(self) -> Optional[str]:
        return self._decoded[2]

    @property
    def magic(self) -> bytes:
        """First 4 decoded bytes, inflating only the first zlib block."""
        if not _has_zlib_header(self.stored):
            return self.stored[:4]
        return zlib.decompressobj().decompress(self.stored, 4)[:4]

    @property
    def stored_sha256(self) -> str:
        return sha256(self.stored)

    def summary(self) -> dict:
        return {"index": self.index, "name": self.name, "type_hash": f"0x{self.type_hash:08X}",
                "compressed_size": self.compressed_size, "raw_size": self.raw_size,
                "flags": self.flags, "payload_offset": self.payload_offset,
                "stored_sha256": self.stored_sha256}


@dataclass(frozen=True)
class Archive:
    data: bytes
    entries: tuple[Entry, ...]
    strict: bool
    anomalies: tuple[str, ...] = field(default=())

    # ----------------------------------------------------------- lookups
    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __getitem__(self, index: int) -> Entry:
        return self.entries[index]

    @property
    def sha256(self) -> str:
        return sha256(self.data)

    def find(self, key: "int | str", *, magic: Optional[bytes] = None,
             type_hash: Optional[int] = None) -> Entry:
        """Exactly one member by index, exact name, or name suffix
        (optionally narrowed by decoded magic / type hash)."""
        if isinstance(key, int):
            return self.entries[key]
        hits = [e for e in self.entries if e.name == key] or \
               [e for e in self.entries if e.name.lower().endswith(key.lower().replace("/", "\\"))]
        if magic is not None:
            hits = [e for e in hits if e.magic == magic]
        if type_hash is not None:
            hits = [e for e in hits if e.type_hash == type_hash]
        if len(hits) != 1:
            raise ArcError(f"member {key!r} matched {len(hits)} entries")
        return hits[0]

    def by_magic(self, magic: bytes) -> list[Entry]:
        return [e for e in self.entries if e.magic == magic]

    def pair(self, entry: Entry, magic: bytes) -> Optional[Entry]:
        """The sibling resource with the same name and a different magic
        (e.g. the FIM that belongs to a GSM)."""
        for e in self.entries:
            if e.name == entry.name and e.index != entry.index and e.magic == magic:
                return e
        return None

    @property
    def alignment(self) -> int:
        return detect_alignment(self.entries)

    # ---------------------------------------------------------- mutation
    def rebuild(self, replacements: Mapping[int, bytes]) -> bytes:
        if not self.strict:
            raise ArcError("refusing to mutate an archive that only passed lenient inspect(): "
                           + "; ".join(self.anomalies))
        return rebuild(self.data, replacements)


def _parse(data: bytes, strict: bool) -> Archive:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("ARC input must be bytes")
    data = bytes(data)
    if len(data) < 8 or data[:4] != MAGIC:
        raise ArcError("expected PS3 big-endian ARC header")
    version, count = struct.unpack_from(">HH", data, 4)
    if version != VERSION:
        raise ArcError(f"unsupported ARC version: {version}")
    table_end = TABLE_START + count * ENTRY_SIZE
    if table_end > len(data):
        raise ArcError("ARC entry table exceeds source")
    entries = []
    for index in range(count):
        start = TABLE_START + index * ENTRY_SIZE
        record = data[start:start + ENTRY_SIZE]
        type_hash, size, packed, offset = struct.unpack_from(">IIII", record, 64)
        if offset < table_end or offset + size > len(data):
            raise ArcError(f"member {index}: payload range outside ARC")
        name = record[:64].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        entries.append(Entry(index, name, type_hash, size, packed, offset, record,
                             data[offset:offset + size]))
    anomalies = []
    cursor = table_end
    for e in sorted(entries, key=lambda x: (x.payload_offset, x.index)):
        if e.payload_offset < cursor:
            raise ArcError(f"member {e.index}: overlapping payloads")
        if any(data[cursor:e.payload_offset]):
            anomalies.append(f"nonzero ARC gap: {cursor:#x}..{e.payload_offset:#x}")
        cursor = e.payload_offset + e.compressed_size
    if any(data[cursor:]):
        anomalies.append(f"nonzero ARC trailer at {cursor:#x}")
    if strict and anomalies:
        raise ArcError(anomalies[0])
    arc = Archive(data, tuple(entries), strict=not anomalies, anomalies=tuple(anomalies))
    if strict:  # safe_arc validates every stream at parse time
        for e in arc.entries:
            e.raw  # noqa: B018 -- force validation
    return arc


def read(data: bytes) -> Archive:
    """Strict parse (mutation-safe). Validates every member's storage."""
    return _parse(data, strict=True)


def inspect(data: bytes) -> Archive:
    """Lenient, read-only parse. Gaps/trailers become ``anomalies``; members
    are inflated lazily and only on access."""
    return _parse(data, strict=False)


def detect_alignment(entries: Iterable[Entry]) -> int:
    entries = list(entries)
    if not entries:
        return 1
    for a in ALIGNMENTS:
        if all(e.payload_offset % a == 0 for e in entries):
            return a
    return 1


def _effective(entries: tuple[Entry, ...], replacements: Mapping[int, bytes]) -> dict[int, bytes]:
    out = {}
    for index, raw in replacements.items():
        if type(index) is not int or not 0 <= index < len(entries):
            raise ArcError(f"unknown replacement index: {index!r}")
        if not isinstance(raw, bytes):
            raise TypeError(f"replacement {index} must be immutable bytes")
        if len(raw) > 0x1FFFFFFF:
            raise ArcError(f"replacement {index} exceeds packed-size range")
        e = entries[index]
        if e.warning and len(raw) != len(e.raw):
            raise ArcError(f"member {index}: declared-size mismatch prohibits changing actual decoded length")
        if raw != e.raw:
            out[index] = raw
    return out


def rebuild(data: bytes, replacements: Mapping[int, bytes]) -> bytes:
    """Rebuild exact source bytes; untouched stored payloads stay verbatim,
    physical order and alignment are preserved, output is re-verified."""
    arc = read(data)
    eff = _effective(arc.entries, replacements)
    if not eff:
        return arc.data
    ordered = sorted(arc.entries, key=lambda e: (e.payload_offset, e.index))
    alignment = detect_alignment(arc.entries)
    out = bytearray(arc.data[:ordered[0].payload_offset])
    for e in ordered:
        raw = eff.get(e.index)
        if raw is None:
            stored, packed = e.stored, e.packed_size
        else:
            stored = zlib.compress(raw, 9) if e.codec == "zlib" else raw
            packed = e.packed_size if len(raw) == len(e.raw) else (len(raw) << 3) | e.flags
        offset = -(-len(out) // alignment) * alignment
        out.extend(b"\0" * (offset - len(out)))
        out.extend(stored)
        struct.pack_into(">III", out, TABLE_START + e.index * ENTRY_SIZE + 68, len(stored), packed, offset)
    old_end = max(e.payload_offset + e.compressed_size for e in arc.entries)
    out.extend(arc.data[old_end:])
    result = bytes(out)
    verify_rebuild(arc.data, result, eff)
    return result


def verify_rebuild(source: bytes, output: bytes, replacements: Mapping[int, bytes]) -> dict:
    """Re-parse both archives and prove the preservation contract."""
    before, after = read(source), read(output)
    eff = _effective(before.entries, replacements)
    if source[:8] != output[:8] or len(before) != len(after):
        raise ArcError("ARC header/version/count changed")
    if not eff and source != output:
        raise ArcError("effective no-op changed archive bytes")
    changed = []
    for old, new in zip(before, after, strict=False):
        if old.record[:68] != new.record[:68] or old.flags != new.flags:
            raise ArcError(f"member {old.index}: protected metadata changed")
        want = eff.get(old.index)
        if want is None:
            if old.record[68:76] != new.record[68:76] or old.stored != new.stored:
                raise ArcError(f"untouched member {old.index}: stored bytes/size changed")
        else:
            if new.raw != want or new.codec != old.codec:
                raise ArcError(f"member {old.index}: replacement did not round-trip")
            exp_packed = old.packed_size if len(want) == len(old.raw) else (len(want) << 3) | old.flags
            if new.packed_size != exp_packed:
                raise ArcError(f"member {old.index}: packed-size contract changed")
            changed.append({"index": old.index, "name": old.name,
                            "before_raw_sha256": sha256(old.raw), "after_raw_sha256": sha256(new.raw),
                            "before_stored_sha256": old.stored_sha256, "after_stored_sha256": new.stored_sha256})
    order = lambda a: [e.index for e in sorted(a.entries, key=lambda e: (e.payload_offset, e.index))]
    if order(before) != order(after):
        raise ArcError("physical payload ordering changed")
    alignment = detect_alignment(before.entries)
    if any(e.payload_offset % alignment for e in after):
        raise ArcError("payload alignment changed")
    return {"source_sha256": sha256(source), "output_sha256": sha256(output),
            "member_count": len(before), "changed_member_count": len(changed),
            "untouched_stored_verified": len(before) - len(changed), "alignment": alignment,
            "changes": changed,
            "warnings": [{"index": e.index, "name": e.name, "warning": e.warning}
                         for e in before if e.warning]}


def build(members: Iterable[tuple], *, compress: bool = True, alignment: int = 16) -> bytes:
    """Author a fresh ARC (tests/fixtures/tools).
    members = (name, type_hash, raw[, compress_this_member])."""
    members = list(members)
    table_end = TABLE_START + len(members) * ENTRY_SIZE
    out = bytearray(MAGIC + struct.pack(">HH", VERSION, len(members)) + bytes(len(members) * ENTRY_SIZE))
    for i, (name, type_hash, raw, *opt) in enumerate(members):
        stored = zlib.compress(raw, 9) if (opt[0] if opt else compress) else raw
        off = -(-max(len(out), table_end) // alignment) * alignment
        out.extend(b"\0" * (off - len(out)))
        out.extend(stored)
        rec = name.encode("utf-8")[:63].ljust(64, b"\0") + struct.pack(">IIII", type_hash, len(stored), len(raw) << 3, off)
        out[TABLE_START + i * ENTRY_SIZE: TABLE_START + (i + 1) * ENTRY_SIZE] = rec
    return bytes(out)
