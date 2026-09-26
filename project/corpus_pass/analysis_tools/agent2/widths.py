"""Per-speech line widths. basara.font.measure() does not start a new line at {p} (0xFFFD), so a
speech's last line and the next speech's first line are summed; this splits at both {br} and {p}."""
from basara.msg import BR, SPEECH, GLYPH_LIMIT, WESTERN, tokenize
def speech_widths(words, tnf, grammar=WESTERN):
    out, cur, line = [], [], 0
    for t in tokenize(words, grammar):
        if t.word == BR:
            cur.append(line); line = 0
        elif t.word == SPEECH:
            cur.append(line); out.append(cur); cur, line = [], 0
        elif t.word < GLYPH_LIMIT:
            line += tnf.advance(t.word) or 0
    cur.append(line)
    if any(cur): out.append(cur)
    return out
def max_line(words, tnf, grammar=WESTERN):
    return max((w for sp in speech_widths(words, tnf, grammar) for w in sp), default=0)
