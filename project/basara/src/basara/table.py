"""One message table (GSM + its FIM + a font) edited as text.

    t = MessageTable.open(archive, "id_brief_r")        # detects the grammar
    t.text(1464)              -> "Sacred Tree Bow: First Frost{end}"
    t.set(1464, "Sacred Tree Bow:{br}First Frost{end}")
    t.width(1464)             -> LineMetrics(widths=(412, 388), ...)
    members = t.build()       -> {gsm_index: bytes, fim_index: bytes}

``build`` re-derives col0/col1 for every FIM row from the final GSM and then
re-checks the whole table under the detected grammar, so a text edit can
never desynchronise the reveal budget or speech offsets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import arc as arcmod
from .font import Csa, LineMetrics, Tnf, measure, CSA_MAGIC, TNF_MAGIC
from .markup import decode, encode
from .msg import FIM_MAGIC, GRAMMARS, GSM_MAGIC, Fim, Gsm, MsgError, apply, check, detect_grammar


@dataclass(frozen=True)
class FontRef:
    tnf: Optional[int] = None
    csa: Optional[int] = None


def resolve_font(archive: arcmod.Archive, font: Optional[FontRef] = None,
                 font_archive: Optional[arcmod.Archive] = None) -> tuple[Optional[Tnf], Optional[Csa]]:
    """Explicit indices win; otherwise the archive's single TNF/CSA pair."""
    src = font_archive or archive
    font = font or FontRef()
    tnfs = [font.tnf] if font.tnf is not None else [e.index for e in src.by_magic(TNF_MAGIC)]
    csas = [font.csa] if font.csa is not None else [e.index for e in src.by_magic(CSA_MAGIC)]
    tnf = Tnf.parse(src[tnfs[0]].raw) if len(tnfs) == 1 else None
    csa = Csa.parse(src[csas[0]].raw) if len(csas) == 1 else None
    return tnf, csa


@dataclass
class MessageTable:
    archive: arcmod.Archive
    gsm_entry: arcmod.Entry
    fim_entry: Optional[arcmod.Entry]
    gsm: Gsm
    fim: Optional[Fim]
    grammar_name: str
    tnf: Optional[Tnf] = None
    csa: Optional[Csa] = None
    _edits: dict = field(default_factory=dict)

    @classmethod
    def open(cls, archive: arcmod.Archive, table: "int | str", *, font: Optional[FontRef] = None,
             font_archive: Optional[arcmod.Archive] = None, grammar: Optional[str] = None) -> "MessageTable":
        g = archive.find(table, magic=GSM_MAGIC) if isinstance(table, str) else archive[table]
        if g.magic != GSM_MAGIC:
            raise MsgError(f"member {g.index} ({g.name}) is not a GSM table")
        f = archive.pair(g, FIM_MAGIC)
        gsm = Gsm.parse(g.raw)
        fim = Fim.parse(f.raw) if f is not None else None
        if grammar is None:
            grammar = detect_grammar(gsm, fim) if fim is not None else "western"
        tnf, csa = resolve_font(archive, font, font_archive)
        return cls(archive, g, f, gsm, fim, grammar, tnf, csa)

    @property
    def grammar(self):
        return GRAMMARS[self.grammar_name]

    def __len__(self) -> int:
        return len(self.gsm)

    def words(self, record: int) -> tuple[int, ...]:
        return tuple(self._edits.get(record, self.gsm.words(record)))

    def text(self, record: int) -> str:
        return decode(self.words(record), self.csa, self.grammar)

    def set(self, record: int, markup: str) -> None:
        if not 0 <= record < len(self.gsm):
            raise MsgError(f"record {record} out of range 0..{len(self.gsm) - 1}")
        self._edits[record] = tuple(encode(markup, self.csa, self.grammar))

    def width(self, record: int) -> Optional[LineMetrics]:
        return measure(self.words(record), self.tnf, self.grammar) if self.tnf else None

    @property
    def edited(self) -> list[int]:
        return sorted(r for r, w in self._edits.items() if w != self.gsm.words(r))

    def build(self) -> dict[int, bytes]:
        """Member replacements for the archive. Raises if the result would
        violate the FIM contract anywhere in the table."""
        new_gsm = self.gsm.with_records(self._edits)
        out = {self.gsm_entry.index: new_gsm.to_bytes()}
        if self.fim is not None:
            new_fim = apply(new_gsm, self.fim, self.grammar)
            rep = check(new_gsm, new_fim, self.grammar_name)
            if not rep.ok:
                raise MsgError(f"contract check failed after edit: {rep.violations[:3]} {rep.errors[:1]}")
            out[self.fim_entry.index] = new_fim.to_bytes()
        return {i: b for i, b in out.items() if b != self.archive[i].raw}
