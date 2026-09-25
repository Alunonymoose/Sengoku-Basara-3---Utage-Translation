"""Translation catalogs: tables as spreadsheet-friendly TSV, linted before build.

    basara catalog export equip.arc id_brief_r -o brief.tsv [--ref jpn/equip.arc]
    (translators fill the `translation` column in any spreadsheet)
    basara catalog lint   brief.tsv --arc equip.arc [--budget 700] [--terms terminology.json]
    basara catalog import brief.tsv --arc equip.arc --arc-path tenka/equip.arc -o patch.toml

Columns: record | current | reference | translation | note
`current` is the live markup (it becomes the patchset's `expect` stale guard).
Standard excel-tab dialect, so Excel / Google Sheets / LibreOffice open it directly.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .markup import MarkupError, placeables
from .msg import MsgError
from .table import MessageTable

COLUMNS = ["record", "current", "reference", "translation", "note"]


def export(table: MessageTable, reference: Optional[MessageTable] = None, *,
           only_nonempty: bool = True) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, dialect="excel-tab", lineterminator="\n")
    w.writerow(COLUMNS)
    for r in range(len(table)):
        cur = table.text(r)
        if only_nonempty and cur in ("", "{end}"):
            continue
        ref = ""
        if reference is not None and r < len(reference):
            try:
                ref = reference.text(r)
            except (MsgError, MarkupError):
                ref = "<undecodable>"
        w.writerow([r, cur, ref, "", ""])
    return buf.getvalue()


def read(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text), dialect="excel-tab"))
    missing = set(COLUMNS[:4]) - set(rows[0].keys() if rows else COLUMNS)
    if missing:
        raise ValueError(f"catalog is missing columns {sorted(missing)}")
    for row in rows:
        row["record"] = int(row["record"])
    return rows


@dataclass
class Finding:
    record: int
    level: str        # ERROR blocks build; WARN needs review
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:5} #{self.record:<5} {self.code:<18} {self.message}"


def _terms(path: Optional[Path]) -> list[tuple[str, str, re.Pattern]]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        canon = e.get("canonical_english")
        for bad in e.get("forbidden_or_superseded_variants", []) or []:
            if bad and canon and bad != canon:
                out.append((bad, canon, re.compile(r"(?<![A-Za-z])" + re.escape(bad) + r"(?![A-Za-z])")))
    return out


def lint(rows: list[dict], table: MessageTable, *, budget: Optional[int] = None,
         terms_path: Optional[Path] = None) -> list[Finding]:
    """Everything that would otherwise surface as a broken screen in RPCS3."""
    terms = _terms(terms_path)
    out: list[Finding] = []
    for row in rows:
        r, new = row["record"], (row.get("translation") or "").strip()
        if not new:
            continue
        if not 0 <= r < len(table):
            out.append(Finding(r, "ERROR", "no-such-record", f"table has {len(table)} records"))
            continue
        live = table.text(r)
        if row["current"] != live:
            out.append(Finding(r, "ERROR", "stale", f"live text changed since export: {live!r}"))
        missing = table.csa.missing(re.sub(r"\{[^{}]*\}", "", new.replace("{{", "").replace("}}", ""))) if table.csa else []
        if missing:
            out.append(Finding(r, "ERROR", "font-coverage", f"not in this font: {''.join(missing)!r}"))
            continue
        if placeables(new) != placeables(live):
            out.append(Finding(r, "ERROR", "placeables", f"structure changed: {placeables(live)} -> {placeables(new)}"))
        probe = MessageTable(table.archive, table.gsm_entry, table.fim_entry, table.gsm, table.fim,
                             table.grammar_name, table.tnf, table.csa)
        try:
            probe.set(r, new)
            probe.build()
        except (MarkupError, MsgError) as exc:
            out.append(Finding(r, "ERROR", "encode/contract", str(exc)))
            continue
        m = probe.width(r)
        if m is not None:
            if budget is not None and m.max_width > budget:
                out.append(Finding(r, "ERROR", "width", f"line widths {list(m.widths)} > budget {budget}"))
            old = table.width(r)
            if old is not None and m.lines > old.lines:
                out.append(Finding(r, "WARN", "extra-lines", f"{old.lines} -> {m.lines} visual lines"))
            if m.unknown_glyphs:
                out.append(Finding(r, "WARN", "unknown-width", f"{m.unknown_glyphs} glyphs without TNF metrics"))
        plain = re.sub(r"\{[^{}]*\}", " ", new)
        for bad, canon, rx in terms:
            if rx.search(plain):
                out.append(Finding(r, "ERROR", "terminology", f"{bad!r} -> use {canon!r}"))
        if re.search(r" {2}", new) or re.search(r" (\{(br|p|end)\}|$)", new):
            out.append(Finding(r, "WARN", "whitespace", "double space, or space before a break/end"))
    return out


def to_patchset(rows: list[dict], *, patch_id: str, arc_path: str, arc_sha256: str, table: str,
                budget: Optional[int] = None) -> str:
    """TOML patchset for every row whose translation differs from current."""
    def q(s: str) -> str:
        return json.dumps(s, ensure_ascii=False)
    lines = ['schema = "basara.patchset/1"', f"id = {q(patch_id)}", "", "[[archive]]",
             f"path = {q(arc_path)}", f"sha256 = {q(arc_sha256)}"]
    n = 0
    for row in rows:
        new = (row.get("translation") or "").strip()
        if not new or new == row["current"]:
            continue
        lines += ["", "  [[archive.text]]", f"  table = {q(table)}", f"  record = {row['record']}",
                  f"  expect = {q(row['current'])}", f"  text = {q(new)}"]
        if budget is not None:
            lines.append(f"  budget = {budget}")
        n += 1
    if not n:
        raise ValueError("no changed translations in catalog")
    return "\n".join(lines) + "\n"
