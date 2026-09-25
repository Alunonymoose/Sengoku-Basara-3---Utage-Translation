"""Lossless, human-editable markup for GSM word runs.

    decode(words) -> "Use {c:3}Release{/c} to escape{br}the ambush{end}"
    encode(text)  -> exactly the original words

Round trip is guaranteed by construction: a word is shown as a character only
if encoding that character yields the same word; otherwise it is shown as a
tag. Property-tested over random word runs.

Tags (hex arguments, case-insensitive):
  {br}          0xFFFE  new visual line (a literal newline also encodes to it)
  {p}           0xFFFD  next speech / page
  {end}         0xFFFF  terminator
  {c:N} {/c}    0xFF92 N / 0xFF91   colour span (western grammar)
  {spk:N}       0xFC0D N            speaker / portrait
  {g:XXXX}      glyph ordinal with no character in this font's CSA
  {ref:XXXX}    0xD000-0xEFFF reference / icon word
  {w:XXXX}      any other non-control word (0x8000-0xCFFF)
  {XXXX:a,b}    any other control word with its arguments
  {{  }}        literal braces
"""
from __future__ import annotations

import re
from typing import Mapping, Optional, Sequence

from .font import Csa
from .msg import (BR, COLOUR_CLOSE, COLOUR_OPEN, CONTROL_MIN, END, REF_MAX, REF_MIN, SPEAKER, SPEECH,
                  WESTERN, MsgError, tokenize)

_NAMED0 = {BR: "br", SPEECH: "p", END: "end"}
_NAMED_WORD = {v: k for k, v in _NAMED0.items()}
_TAG = re.compile(r"\{([^{}]*)\}")


class MarkupError(ValueError):
    pass


def decode(words: Sequence[int], csa: Optional[Csa], grammar: Mapping[int, int] = WESTERN) -> str:
    inv = csa.inverse() if csa is not None else {0: " "}
    out = []
    for t in tokenize(words, grammar):
        w = t.word
        if w >= CONTROL_MIN:
            if w in _NAMED0 and not t.args:
                out.append("{" + _NAMED0[w] + "}")
            elif w == COLOUR_OPEN and len(t.args) == 1:
                out.append(f"{{c:{t.args[0]:X}}}")
            elif w == COLOUR_CLOSE and not t.args:
                out.append("{/c}")
            elif w == SPEAKER and len(t.args) == 1:
                out.append(f"{{spk:{t.args[0]:X}}}")
            else:
                args = ",".join(f"{a:X}" for a in t.args)
                out.append(f"{{{w:04X}" + (f":{args}" if args else "") + "}")
        elif REF_MIN <= w <= REF_MAX:
            out.append(f"{{ref:{w:04X}}}")
        elif w >= 0x8000:
            out.append(f"{{w:{w:04X}}}")
        else:
            ch = inv.get(w)
            if ch is not None and _encode_char(ch, csa) == w:
                out.append("{{" if ch == "{" else "}}" if ch == "}" else ch)
            else:
                out.append(f"{{g:{w:04X}}}")
    return "".join(out)


def _encode_char(ch: str, csa: Optional[Csa]) -> Optional[int]:
    if ch == " ":
        return 0
    return csa.ordinal(ch) if csa is not None else None


def _hex(s: str, what: str) -> int:
    try:
        v = int(s, 16)
    except ValueError:
        raise MarkupError(f"bad hex {s!r} in {what}") from None
    if not 0 <= v <= 0xFFFF:
        raise MarkupError(f"{what}: {s!r} out of u16 range")
    return v


def encode(text: str, csa: Optional[Csa], grammar: Mapping[int, int] = WESTERN) -> list[int]:
    words: list[int] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if text.startswith("{{", i):
            words.append(_char(csa, "{"))
            i += 2
            continue
        if text.startswith("}}", i):
            words.append(_char(csa, "}"))
            i += 2
            continue
        if ch == "{":
            m = _TAG.match(text, i)
            if not m:
                raise MarkupError(f"unclosed tag at {i}: {text[i:i + 12]!r}")
            words.extend(_tag(m.group(1)))
            i = m.end()
            continue
        if ch == "}":
            raise MarkupError(f"stray '}}' at {i}")
        if ch == "\n":
            words.append(BR)
            i += 1
            continue
        words.append(_char(csa, ch))
        i += 1
    try:
        tokenize(words, grammar)
    except MsgError as exc:
        raise MarkupError(f"encoded run is not valid under the table grammar: {exc}") from None
    return words


def _char(csa: Optional[Csa], ch: str) -> int:
    w = _encode_char(ch, csa)
    if w is None:
        raise MarkupError(f"character {ch!r} (U+{ord(ch):04X}) is not in this font's CSA")
    return w


def _tag(body: str) -> list[int]:
    name, _, arg = body.partition(":")
    key = name.strip().lower()
    if key in _NAMED_WORD and not arg:
        return [_NAMED_WORD[key]]
    if key == "/c" and not arg:
        return [COLOUR_CLOSE]
    if key == "c":
        return [COLOUR_OPEN, _hex(arg, "{c:}")]
    if key == "spk":
        return [SPEAKER, _hex(arg, "{spk:}")]
    if key == "g":
        w = _hex(arg, "{g:}")
        if w >= 0x8000:
            raise MarkupError("{g:} must be a glyph ordinal < 0x8000")
        return [w]
    if key == "ref":
        w = _hex(arg, "{ref:}")
        if not REF_MIN <= w <= REF_MAX:
            raise MarkupError("{ref:} must be 0xD000-0xEFFF")
        return [w]
    if key == "w":
        w = _hex(arg, "{w:}")
        if not 0x8000 <= w < CONTROL_MIN or REF_MIN <= w <= REF_MAX:
            raise MarkupError("{w:} must be 0x8000-0xCFFF")
        return [w]
    w = _hex(name, "control tag")
    if w < CONTROL_MIN:
        raise MarkupError(f"unknown tag {{{body}}}")
    return [w] + ([_hex(a, "control argument") for a in arg.split(",")] if arg else [])


def placeables(text: str) -> list[str]:
    """Structural tags a translation must preserve (in order), used by lint:
    speech breaks, terminators, speakers, colour spans and raw controls.
    Line breaks are layout, not structure, so they are excluded."""
    out = []
    for m in _TAG.finditer(text.replace("{{", "").replace("}}", "")):
        k = m.group(1).split(":")[0].lower()
        if k in ("br", "g"):
            continue
        out.append("{" + m.group(1).lower() + "}")
    return out
