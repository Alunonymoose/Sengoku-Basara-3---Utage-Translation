"""Corpus access for the agent2 text polish pass (read-only; uses only basara APIs).

The text corpus holds extracted GSM/FIM/CSA members per ARC (no full ARCs). For offline
verification we rebuild a *stand-in* ARC per live archive with basara.arc.build(): every text
member and the font pair sit at their REAL member indices and names (gaps padded), so
`basara build` on a patchset whose sha256 is swapped to the stand-in exercises exactly the same
table lookup / font resolution / FIM re-derivation as on the live ARC.

    CORPUS=<scratchpad>/corpus FONTS=<scratchpad>/r2/fonts python -c "import corpus"
"""
from __future__ import annotations

import collections
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from basara import arc as arcmod
from basara.font import Csa, Tnf
from basara.table import FontRef, MessageTable

CORPUS = Path(os.environ.get("CORPUS", "corpus"))
FONTS = Path(os.environ.get("FONTS", "r2/fonts"))
SKIP = re.compile(r"BACKUP|backup|Copy|PRE_", re.I)

M = json.loads((CORPUS / "MANIFEST.json").read_text())["files"]
FM = json.loads((FONTS / "FONTS_MANIFEST.json").read_text())

by_arc = collections.defaultdict(list)          # (tree, arc) -> [file]
for f in M:
    by_arc[(f["tree"], f["arc"])].append(f)
tnf_owner = {}                                   # (arc, index) -> tnf path
for x in FM:
    if x["kind"] == "tnf":
        for o in x["owners"]:
            a, i = o.rsplit("#", 1)
            tnf_owner[(a, int(i))] = FONTS / x["path"]


def live_arcs(tree: str = "utage_eng") -> list[str]:
    return sorted({a for (t, a) in by_arc if t == tree and not SKIP.search(a)
                   and any(f["kind"] == "gsm" for f in by_arc[(t, a)])})


def arc_sha(arc: str, tree: str = "utage_eng") -> str:
    return by_arc[(tree, arc)][0]["arc_sha256"]


def fonts(arc: str, tree: str = "utage_eng") -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    csas = sorted((f["index"], f["name"]) for f in by_arc[(tree, arc)] if f["kind"] == "csa")
    tnfs = sorted(i for (a, i) in tnf_owner if a == arc)
    return [(i, "") for i in tnfs], csas


def font_for(arc: str, table_name: str) -> FontRef | None:
    """Explicit font pair for archives holding several (jpn/eng duplicates); None = the single pair."""
    tnfs, csas = fonts(arc)
    if len(csas) <= 1 and len(tnfs) <= 1:
        return None
    d = table_name.rsplit("\\", 1)[0]
    c = [i for i, n in csas if n.rsplit("\\", 1)[0] == d]
    if len(c) != 1:   # e.g. captions: use the ascii font of the same language directory
        lang = table_name.split("\\")[2] if table_name.count("\\") >= 3 else ""
        c = [i for i, n in csas if n.count("\\") >= 3 and n.split("\\")[2] == lang][:1]
    if len(c) != 1:
        return None
    # the TNF is the member just before its CSA's text block: pick the nearest TNF index below the CSA
    below = [i for i, _ in tnfs if i < c[0]]
    return FontRef(tnf=max(below), csa=c[0]) if below else None


@lru_cache(maxsize=64)
def standin(arc: str, tree: str = "utage_eng") -> bytes:
    files = [f for f in by_arc[(tree, arc)] if f["kind"] in ("gsm", "fim", "csa")]
    members = {f["index"]: (f["name"], (CORPUS / f["path"]).read_bytes()) for f in files}
    if tree == "utage_eng":
        for (a, i), p in tnf_owner.items():
            if a == arc:
                members[i] = (f"font_tnf_{i}", p.read_bytes())
    n = max(members) + 1
    return arcmod.build([(members[i][0], 0, members[i][1]) if i in members else (f"pad_{i}", 0, b"PAD\0")
                         for i in range(n)])


@lru_cache(maxsize=64)
def archive(arc: str, tree: str = "utage_eng") -> arcmod.Archive:
    return arcmod.read(standin(arc, tree))


def tables(arc: str, tree: str = "utage_eng") -> list[str]:
    return [f["name"] for f in sorted(by_arc[(tree, arc)], key=lambda f: f["index"]) if f["kind"] == "gsm"]


def open_table(arc: str, name: str, tree: str = "utage_eng") -> MessageTable:
    a = archive(arc, tree)
    fr = font_for(arc, name) if tree == "utage_eng" else None
    if tree != "utage_eng":
        return MessageTable.open(a, a.find(name, magic=b"\x00GSM").index)
    return MessageTable.open(a, a.find(name, magic=b"\x00GSM").index, font=fr)
