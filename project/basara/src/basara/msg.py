"""GSM message tables, FIM format tables, control grammar and the FIM contract.

GSM ``\\0GSM`` (big-endian)
    +0 magic, +4 u32 (preserved), +8 pool_units, +12 record_count,
    record_count x (u32 offset, u32 length) in u16 units, then the u16 pool.
    ``16 + count*8 + pool*2 == len`` exactly. Pool words beyond the last
    referenced word are preserved padding.

FIM ``\\0FIM`` (big-endian)
    +8 n_primary, +12 n_secondary, +16 n_voices, header padded to 32 bytes
    (preserved), n_primary x 5 u32, n_secondary x 11 u32. Exact size.
    primary[r].col3 >> 16 = speech count, primary[r].col4 = first secondary row.

THE CONTRACT (zero exceptions on 1,469,782 pristine JP + 246,404 official SH
format rows, FIM_CONTRACT_REPAIR 2026-09-20), for speech k of record r,
secondary row j = primary[r].col4 + k:
    col0        = (visual_lines << 16) | visible_glyphs
    col1 >> 16  = start offset of the speech inside its record (u16 units)
  visible glyph = token word < 0x8000 (control arguments are never glyphs)
  visual_lines  = 1 + number of 0xFFFE in the speech
  speeches start at 0 and after every 0xFFFD that is not the final
  terminator position; their number must equal primary[r].col3 >> 16.

Grammar = argument count per control word (>= 0xF000). Two tables exist in
the corpus; ``detect_grammar`` picks the one with ZERO contract violations on
the untouched table and fails closed if none does.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

GSM_MAGIC = b"\x00GSM"
FIM_MAGIC = b"\x00FIM"

CONTROL_MIN = 0xF000
REF_MIN, REF_MAX = 0xD000, 0xEFFF
GLYPH_LIMIT = 0x8000          # contract: visible glyph <=> word < 0x8000
BR, SPEECH, END = 0xFFFE, 0xFFFD, 0xFFFF
COLOUR_OPEN, COLOUR_CLOSE = 0xFF92, 0xFF91
SPEAKER = 0xFC0D

#: Corpus-validated grammar (FIM_CONTRACT_REPAIR + FC0D from drama tables).
WESTERN: Mapping[int, int] = {
    0xFC0D: 1, 0xFC0E: 2, 0xFC0F: 1, 0xFC12: 0, 0xFC16: 1, 0xFC17: 3,
    0xFED2: 2, 0xFF91: 0, 0xFF92: 1, 0xFFFA: 1, 0xFFFB: 1,
    0xFFFD: 0, 0xFFFE: 0, 0xFFFF: 0,
}
#: The MASTER-HANDOVER variant (FF92:2, FF91:1). Kept only so detection can
#: prove which one a table uses; it eats the first letter of highlighted
#: words on tables that are really WESTERN.
LEGACY: Mapping[int, int] = {**WESTERN, 0xFF92: 2, 0xFF91: 1}
GRAMMARS: Mapping[str, Mapping[int, int]] = {"western": WESTERN, "legacy": LEGACY}


class MsgError(ValueError):
    pass


# ------------------------------------------------------------------- GSM
@dataclass(frozen=True)
class Gsm:
    header_word: int
    records: tuple[tuple[int, int], ...]
    pool: tuple[int, ...]

    @classmethod
    def parse(cls, blob: bytes) -> "Gsm":
        if len(blob) < 16 or blob[:4] != GSM_MAGIC:
            raise MsgError("not a GSM table")
        hw, pool_units, count = struct.unpack_from(">III", blob, 4)
        if 16 + count * 8 + pool_units * 2 != len(blob):
            raise MsgError(f"GSM size check failed: {16 + count * 8 + pool_units * 2} != {len(blob)}")
        recs = tuple(struct.unpack_from(">II", blob, 16 + i * 8) for i in range(count))
        pool = struct.unpack_from(f">{pool_units}H", blob, 16 + count * 8)
        for i, (o, n) in enumerate(recs):
            if o + n > pool_units:
                raise MsgError(f"record {i} exceeds pool")
        return cls(hw, recs, pool)

    def __len__(self) -> int:
        return len(self.records)

    def words(self, index: int) -> tuple[int, ...]:
        o, n = self.records[index]
        return self.pool[o:o + n]

    def to_bytes(self) -> bytes:
        out = bytearray(GSM_MAGIC + struct.pack(">III", self.header_word, len(self.pool), len(self.records)))
        for o, n in self.records:
            out += struct.pack(">II", o, n)
        out += struct.pack(f">{len(self.pool)}H", *self.pool)
        return bytes(out)

    def with_records(self, changes: Mapping[int, Sequence[int]]) -> "Gsm":
        """Replace record word runs. Same-length edits are written in place
        (byte-minimal); otherwise the pool is repacked in record order and
        trailing padding words are preserved."""
        for i in changes:
            if not 0 <= i < len(self.records):
                raise MsgError(f"unknown record {i}")
        changes = {i: tuple(w) for i, w in changes.items() if tuple(w) != self.words(i)}
        if not changes:
            return self
        if all(len(w) == self.records[i][1] for i, w in changes.items()) and not self._shared(changes):
            pool = list(self.pool)
            for i, w in changes.items():
                o, n = self.records[i]
                pool[o:o + n] = w
            return replace(self, pool=tuple(pool))
        used_end = max((o + n for o, n in self.records), default=0)
        padding = self.pool[used_end:]
        pool: list[int] = []
        recs = []
        for i in range(len(self.records)):
            w = changes.get(i, self.words(i))
            recs.append((len(pool), len(w)))
            pool.extend(w)
        pool.extend(padding)
        return Gsm(self.header_word, tuple(recs), tuple(pool))

    def _shared(self, changes: Mapping[int, Sequence[int]]) -> bool:
        spans = {i: self.records[i] for i in changes}
        for i, (o, n) in enumerate(self.records):
            for j, (co, cn) in spans.items():
                if i != j and o < co + cn and co < o + n:
                    return True
        return False


# ------------------------------------------------------------------- FIM
@dataclass(frozen=True)
class Fim:
    header: bytes                       # 32 bytes, preserved verbatim
    primary: tuple[tuple[int, ...], ...]
    secondary: tuple[tuple[int, ...], ...]

    @classmethod
    def parse(cls, blob: bytes) -> "Fim":
        if len(blob) < 32 or blob[:4] != FIM_MAGIC:
            raise MsgError("not a FIM table")
        n1, n2, _nv = struct.unpack_from(">III", blob, 8)
        if 32 + n1 * 20 + n2 * 44 != len(blob):
            raise MsgError(f"FIM size check failed: {32 + n1 * 20 + n2 * 44} != {len(blob)}")
        p = tuple(struct.unpack_from(">5I", blob, 32 + i * 20) for i in range(n1))
        base = 32 + n1 * 20
        s = tuple(struct.unpack_from(">11I", blob, base + j * 44) for j in range(n2))
        return cls(bytes(blob[:32]), p, s)

    def to_bytes(self) -> bytes:
        out = bytearray(self.header)
        for row in self.primary:
            out += struct.pack(">5I", *row)
        for row in self.secondary:
            out += struct.pack(">11I", *row)
        return bytes(out)

    def speech_count(self, record: int) -> int:
        return self.primary[record][3] >> 16

    def first_row(self, record: int) -> int:
        return self.primary[record][4]


# --------------------------------------------------------------- grammar
@dataclass(frozen=True)
class Token:
    offset: int
    word: int
    args: tuple[int, ...] = ()

    @property
    def is_control(self) -> bool:
        return self.word >= CONTROL_MIN

    @property
    def is_glyph(self) -> bool:
        return self.word < GLYPH_LIMIT

    @property
    def is_ref(self) -> bool:
        return REF_MIN <= self.word <= REF_MAX

    @property
    def width(self) -> int:
        return 1 + len(self.args)


def tokenize(words: Sequence[int], grammar: Mapping[int, int] = WESTERN) -> list[Token]:
    """Split a word run into tokens. Unknown control words and truncated
    arguments are errors (fail closed: an uncharted control word means the
    grammar is not proven for this table)."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if w >= CONTROL_MIN:
            if w not in grammar:
                raise MsgError(f"unknown control word {w:04X} at {i}")
            n = grammar[w]
            if i + 1 + n > len(words):
                raise MsgError(f"truncated control {w:04X} at {i}")
            out.append(Token(i, w, tuple(words[i + 1:i + 1 + n])))
            i += 1 + n
        else:
            out.append(Token(i, w))
            i += 1
    return out


def speech_spans(words: Sequence[int], count: int, grammar: Mapping[int, int] = WESTERN) -> list[tuple[int, int]]:
    toks = tokenize(words, grammar)
    if count == 0:
        if any(t.is_glyph for t in toks):
            raise MsgError("visible text in a zero-speech record")
        return []
    starts = [0] + [t.offset + t.width for t in toks
                    if t.word == SPEECH and t.offset + t.width < len(words) - 1]
    if len(starts) != count:
        raise MsgError(f"speech count {len(starts)} != FIM {count}")
    return [(s, starts[k + 1] if k + 1 < len(starts) else len(words)) for k, s in enumerate(starts)]


def reveal(words: Sequence[int], grammar: Mapping[int, int] = WESTERN) -> tuple[int, int]:
    """(visual_lines, visible_glyphs) of one speech."""
    toks = tokenize(words, grammar)
    return 1 + sum(t.word == BR for t in toks), sum(t.is_glyph for t in toks)


# -------------------------------------------------------------- contract
@dataclass(frozen=True)
class RowValue:
    lines: int
    glyphs: int
    start: int

    @property
    def col0(self) -> int:
        return (self.lines << 16) | self.glyphs


@dataclass
class ContractReport:
    grammar: str
    rows: int
    violations: list = field(default_factory=list)      # (row, want, have)
    errors: list = field(default_factory=list)          # (record, message)
    ambiguous_words: int = 0                            # words 0x8000..0xCFFF seen

    @property
    def ok(self) -> bool:
        return not self.violations and not self.errors


def derive(gsm: Gsm, fim: Fim, grammar: Mapping[int, int] = WESTERN) -> dict[int, RowValue]:
    """Required (col0, col1-high) for every secondary row, from the GSM."""
    if len(fim.primary) != len(gsm):
        raise MsgError(f"FIM/GSM shape mismatch: {len(fim.primary)} primary rows, {len(gsm)} records")
    want: dict[int, RowValue] = {}
    for r in range(len(gsm)):
        words = gsm.words(r)
        first = fim.first_row(r)
        for k, (s, e) in enumerate(speech_spans(words, fim.speech_count(r), grammar)):
            j = first + k
            if j >= len(fim.secondary):
                raise MsgError(f"record {r}: format index {j} out of range")
            lines, glyphs = reveal(words[s:e], grammar)
            val = RowValue(lines, glyphs, s)
            if max(lines, glyphs, s) > 0xFFFF:
                raise MsgError(f"record {r}: halfword overflow")
            if j in want and want[j] != val:
                raise MsgError(f"conflicting shared format row {j}")
            want[j] = val
    return want


def check(gsm: Gsm, fim: Fim, grammar_name: str = "western") -> ContractReport:
    grammar = GRAMMARS[grammar_name]
    rep = ContractReport(grammar_name, len(fim.secondary))
    rep.ambiguous_words = sum(GLYPH_LIMIT <= w < REF_MIN for w in gsm.pool)
    try:
        want = derive(gsm, fim, grammar)
    except MsgError as exc:
        rep.errors.append((None, str(exc)))
        return rep
    for j, v in sorted(want.items()):
        c0, c1 = fim.secondary[j][0], fim.secondary[j][1]
        if c0 != v.col0 or c1 >> 16 != v.start:
            rep.violations.append((j, (v.col0, v.start), (c0, c1 >> 16)))
    unowned = set(range(len(fim.secondary))) - set(want)
    if unowned:
        rep.errors.append((None, f"{len(unowned)} unowned format rows"))
    return rep


def detect_grammar(gsm: Gsm, fim: Fim) -> str:
    """The grammar under which the UNTOUCHED table satisfies the contract.
    Raises if none does -- the table has uncharted structure."""
    results = {name: check(gsm, fim, name) for name in GRAMMARS}
    good = [n for n, r in results.items() if r.ok]
    if not good:
        detail = {n: (len(r.violations), r.errors[:1]) for n, r in results.items()}
        raise MsgError(f"no proven grammar satisfies this table: {detail}")
    return good[0]  # 'western' first: identical tables prefer the corpus grammar


def apply(gsm: Gsm, fim: Fim, grammar: Mapping[int, int] = WESTERN) -> Fim:
    """Return the FIM with col0 and col1-high16 re-derived for every row.
    Nothing else in the FIM changes."""
    want = derive(gsm, fim, grammar)
    if set(want) != set(range(len(fim.secondary))):
        raise MsgError("unowned format rows; refusing to guess their values")
    rows = list(fim.secondary)
    for j, v in want.items():
        row = list(rows[j])
        row[0] = v.col0
        row[1] = (v.start << 16) | (row[1] & 0xFFFF)
        rows[j] = tuple(row)
    return replace(fim, secondary=tuple(rows))
