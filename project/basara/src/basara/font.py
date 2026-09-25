"""TNF glyph metrics, CSA character maps and line-width measurement.

TNF ``\\0TNF``: +8 u32 glyph count, +12 cell width, +16 cell height, records
at 32, 8 bytes each: (glyph_id, atlas_x, atlas_y, advance), big-endian.
Glyphs are addressed by TABLE ORDINAL, never by the ``glyph_id`` field.

CSA ``\\0CSA``: u16 big-endian table at byte 8 indexed directly by codepoint
(``csa[cp] = u16 @ 8 + 2*cp``, valid for cp >= 12 because the first 24
bytes after the magic are header). 0xFFFF = absent. Space encodes as word 0.
(The older "offset 32, codepoint i+12" wording is the same table.)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from .msg import BR, GLYPH_LIMIT, WESTERN, tokenize

TNF_MAGIC = b"\x00TNF"
CSA_MAGIC = b"\x00CSA"
CSA_FIRST_CODEPOINT = 12


class FontError(ValueError):
    pass


@dataclass(frozen=True)
class Glyph:
    glyph_id: int
    atlas_x: int
    atlas_y: int
    advance: int


@dataclass(frozen=True)
class Tnf:
    cell_width: int
    cell_height: int
    glyphs: tuple[Glyph, ...]

    @classmethod
    def parse(cls, blob: bytes) -> "Tnf":
        if len(blob) < 32 or blob[:4] != TNF_MAGIC:
            raise FontError("not a TNF resource")
        count, cw, ch = struct.unpack_from(">III", blob, 8)
        if 32 + count * 8 > len(blob):
            raise FontError("TNF record table exceeds resource")
        glyphs = tuple(Glyph(*struct.unpack_from(">4H", blob, 32 + i * 8)) for i in range(count))
        return cls(cw, ch, glyphs)

    def advance(self, ordinal: int) -> Optional[int]:
        return self.glyphs[ordinal].advance if 0 <= ordinal < len(self.glyphs) else None


@dataclass(frozen=True)
class Csa:
    table: tuple[int, ...]     # index = codepoint

    @classmethod
    def parse(cls, blob: bytes) -> "Csa":
        if len(blob) < 8 or blob[:4] != CSA_MAGIC or (len(blob) - 8) % 2:
            raise FontError("not a CSA resource")
        return cls(struct.unpack(f">{(len(blob) - 8) // 2}H", blob[8:]))

    def ordinal(self, ch: str) -> Optional[int]:
        if ch == " ":
            return 0
        cp = ord(ch)
        if cp < CSA_FIRST_CODEPOINT or cp >= len(self.table):
            return None
        v = self.table[cp]
        return None if v == 0xFFFF else v

    def inverse(self) -> dict[int, str]:
        inv = {0: " "}
        for cp in range(CSA_FIRST_CODEPOINT, len(self.table)):
            v = self.table[cp]
            if v != 0xFFFF and v not in inv:
                inv[v] = chr(cp)
        return inv

    def missing(self, text: str) -> list[str]:
        return sorted({c for c in text if self.ordinal(c) is None})


@dataclass(frozen=True)
class LineMetrics:
    widths: tuple[int, ...]
    unknown_glyphs: int          # ordinals with no TNF record (width unknown)

    @property
    def max_width(self) -> int:
        return max(self.widths, default=0)

    @property
    def lines(self) -> int:
        return len(self.widths)


def measure(words: Sequence[int], tnf: Tnf, grammar: Mapping[int, int] = WESTERN) -> LineMetrics:
    """Per-visual-line width in TNF advance units. Control words and their
    arguments are skipped; 0xFFFE starts a new line; reference/icon words
    (>= 0x8000) are not glyphs and have no TNF width."""
    widths, cur, unknown = [], 0, 0
    for t in tokenize(words, grammar):
        if t.word == BR:
            widths.append(cur)
            cur = 0
        elif t.word < GLYPH_LIMIT:
            adv = tnf.advance(t.word)
            if adv is None:
                unknown += 1
            else:
                cur += adv
    widths.append(cur)
    return LineMetrics(tuple(widths), unknown)
