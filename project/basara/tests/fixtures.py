"""Synthetic game-format fixtures (no game data may live in this public repo).

Tables are generated FROM the contract, so a fixture is by construction what
a shipped Utage table looks like; tests then prove edits keep it that way.
"""
from __future__ import annotations

import struct

from basara import arc as arcmod
from basara.font import Csa
from basara.markup import encode
from basara.msg import GRAMMARS, SPEECH, tokenize, reveal

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;!?'-()/&+%{}"


def csa_blob(chars: str = CHARS, extra: dict | None = None) -> bytes:
    table = [0xFFFF] * 0x100
    for i, ch in enumerate(chars, start=1):
        table[ord(ch)] = i
    table[0x20] = 0
    for cp, v in (extra or {}).items():
        table[cp] = v
    # u16 table at byte 8 indexed by codepoint; entries < 12 overlap the header
    return b"\x00CSA" + bytes(4) + struct.pack(f">{len(table)}H", *table)


def tnf_blob(n: int = len(CHARS) + 1, advance=lambda i: 10 + i % 7) -> bytes:
    out = bytearray(b"\x00TNF" + struct.pack(">IIII", 0, n, 26, 20) + bytes(12))
    for i in range(n):
        out += struct.pack(">4H", i, (i % 16) * 26, (i // 16) * 20, advance(i))
    return bytes(out)


def speech_count(words, grammar) -> int:
    toks = tokenize(words, grammar)
    return 1 + sum(1 for t in toks if t.word == SPEECH and t.offset + t.width < len(words) - 1)


def table_blobs(texts: list[str], csa: Csa, grammar: str = "western", padding: int = 3,
                header_word: int = 0, voice_base: int = 0x00020000) -> tuple[bytes, bytes]:
    """(GSM, FIM) whose FIM rows satisfy the contract for `texts`."""
    g = GRAMMARS[grammar]
    runs = [encode(t, csa, g) for t in texts]
    pool, recs = [], []
    for w in runs:
        recs.append((len(pool), len(w)))
        pool.extend(w)
    pool.extend([0xFFFF] * padding)
    gsm = bytearray(b"\x00GSM" + struct.pack(">III", header_word, len(pool), len(recs)))
    for o, n in recs:
        gsm += struct.pack(">II", o, n)
    gsm += struct.pack(f">{len(pool)}H", *pool)
    primary, secondary = [], []
    for r, w in enumerate(runs):
        count = speech_count(w, g)
        primary.append((r, 0xAAAA, 0, (count << 16) | 0x0055, len(secondary)))
        toks = tokenize(w, g)
        starts = [0] + [t.offset + t.width for t in toks if t.word == SPEECH and t.offset + t.width < len(w) - 1]
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else len(w)
            lines, glyphs = reveal(w[s:e], g)
            row = [0] * 11
            row[0] = (lines << 16) | glyphs
            row[1] = (s << 16) | 0x1234
            row[8] = voice_base | len(secondary)
            row[10] = 0xDEADBEEF
            secondary.append(tuple(row))
    fim = bytearray(b"\x00FIM" + struct.pack(">IIII", 0, len(primary), len(secondary), 7) + bytes(12))
    for row in primary:
        fim += struct.pack(">5I", *row)
    for row in secondary:
        fim += struct.pack(">11I", *row)
    return bytes(gsm), bytes(fim)


def msg_archive(texts: list[str], name: str = r"id\msg\jpn\id_brief_r", grammar: str = "western",
                extra_members: list | None = None) -> bytes:
    csa = Csa.parse(csa_blob())
    gsm, fim = table_blobs(texts, csa, grammar)
    members = [(r"id\font\jpn\font_tnf", 0x11111111, tnf_blob())]
    members += extra_members or []
    members += [(name, 0x22222222, gsm), (name, 0x33333333, fim), (r"id\font\jpn\font_csa", 0x44444444, csa_blob())]
    return arcmod.build(members)


TEXTS = [
    "Sacred Tree Bow: First Frost{end}",
    "Press {c:3}Release{/c} to escape{br}the ambush.{end}",
    "{spk:2}Masamune!{p}{spk:5}Kojuro, follow me.{br}We ride at dawn.{p}Let's go!{end}",
    "{end}",
    "Attack Up +10%{end}",
]
