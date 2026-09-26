"""Mechanical, high-confidence fixes + manual rewrites -> proposals.json {old_markup: {new, reasons}}.

Rules operate on markup text outside tags only; every control tag is kept byte-identical.
Texts excluded: SH-verbatim, undecodable ({g:}), FC0E-injection damaged (repaired separately).
Width: per speech, per line (widths.py). An edit may not create a line wider than
max(old line max, family budget) nor more lines than the family allows; dialogue speeches that
already overflow are re-wrapped (only {br} moved) when a fitting wrap exists.
    python fix.py <work dir>   (needs findings.json, terms.json, rewrites.tsv, typos.json)
"""
import csv, json, re, sys
from pathlib import Path
import corpus as C
from basara.font import Tnf, Csa
from basara.markup import encode, placeables
from widths import speech_widths

W = Path(sys.argv[1])
tnf = Tnf.parse((C.FONTS / "tnf/df843e0b42390e89.tnf").read_bytes())
csa = Csa.parse((C.FONTS / "csa/9d5b493204cae29b.csa").read_bytes())
F = json.loads((W / "findings.json").read_text())
TERMS = json.loads((W / "terms.json").read_text())
NICK = {"Gyobu", "Kingo", "Inuchiyo", "Aniki"}            # nicknames: dialogue families only
TYPOS = json.loads((W / "typos.json").read_text()) if (W / "typos.json").exists() else {}
BUDGET = {"mN_N": 566, "dramaN": 552, "mN_N_r": 527, "id_brief_r": 587, "id_gallery": 443, "id_tenka_r": 423,
          "id_result": 422, "id_gallery_r": 613}
DIALOGUE = {"mN_N", "dramaN"}
FC0E_INJ = re.compile(r"\{FC0E:[^}]*\}[^{]")
TAGSPLIT = re.compile(r"(\{\{|\}\}|\{[^{}]*\})")


def adv(ch):
    o = csa.ordinal(ch)
    return tnf.advance(o) or 0 if o is not None else 0


def textmap(t, fn):
    """Apply fn to the text runs between tags (tags untouched). Tags become placeholders
    \x00<kind><index>\x01 (kind B={br}, P={p}, E={end}, T=other) so regexes cannot alter them."""
    parts = TAGSPLIT.split(t)
    tags, out = [], []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            out.append(p)
        else:
            kind = {"{br}": "B", "{p}": "P", "{end}": "E", "{/c}": "C"}.get(p, "T")
            out.append(f"\x00{kind}{len(tags)}\x01"); tags.append(p)
    new = fn("".join(out))
    return re.sub(r"\x00[BPETC](\d+)\x01", lambda m: tags[int(m.group(1))], new)


def swidths(t):
    return speech_widths(encode(t, csa), tnf)


def rewrap_speech(body, budget, maxlines):
    """body: plain text with {br}; returns a {br}-wrapped body that fits, or None."""
    words = body.replace("{br}", " ").split(" ")
    words = [w for w in words if w != ""]
    if not words: return None
    ws = [sum(adv(c) for c in w) for w in words]
    sp = adv(" ") or 0
    n = len(words)
    best = {n: (0, 0, [])}   # i -> (lines, maxw, breaks)
    for i in range(n - 1, -1, -1):
        cand = None
        width = 0
        for j in range(i, n):
            width += ws[j] + (sp if j > i else 0)
            if width > budget: break
            nl, mw, br = best[j + 1]
            val = (nl + 1, max(mw, width), [j + 1] + br)
            if cand is None or (val[0], val[1]) < (cand[0], cand[1]): cand = val
        if cand is None: best[i] = (10 ** 6, 10 ** 6, []); continue
        best[i] = cand
    nl, mw, br = best[0]
    if nl > maxlines: return None
    lines, s = [], 0
    for e in br:
        lines.append(" ".join(words[s:e])); s = e
    return "{br}".join(lines)


def fit(old, new, fams):
    """Width/line gate; tries re-wrapping dialogue speeches that do not fit. Returns (text, note) or (None, why)."""
    fam = next((f for f in fams if f in BUDGET), None)
    if fam is None:
        return new, ""
    budget = BUDGET[fam]
    maxlines = 3 if fam in DIALOGUE else 99
    ow = swidths(old)
    olimit = max([budget] + [max(sp) for sp in ow if sp])
    nw = swidths(new)
    if all(max(sp) <= budget and len(sp) <= maxlines for sp in nw):
        return new, ""
    if fam not in DIALOGUE:
        if all(max(sp) <= olimit for sp in nw) and max(len(s) for s in nw) <= max(len(s) for s in ow):
            return new, ""
        return None, f"width {max(max(sp) for sp in nw)} > {budget}"
    # re-wrap each offending speech (body between leading and trailing tags, must be tag-free inside)
    pieces = new.split("{p}")
    notes = []
    for k, piece in enumerate(pieces):
        m = re.match(r"^((?:\{(?!br\})[^{}]*\})*)(.*?)((?:\{(?!br\})[^{}]*\})*)$", piece, re.S)
        lead, body, trail = m.groups()
        if not body.strip(): continue
        try:
            w = speech_widths(encode(body, csa), tnf)
        except Exception:
            continue
        if w and max(max(sp) for sp in w) <= budget and max(len(sp) for sp in w) <= maxlines: continue
        if "{" in body.replace("{br}", ""):
            return None, "overflow inside a speech with inline tags"
        rw = rewrap_speech(body, budget, maxlines)
        if rw is None:
            return None, f"cannot wrap into {maxlines} lines <= {budget}"
        pieces[k] = lead + rw + trail
        notes.append("rewrap")
    return "{p}".join(pieces), "rewrapped to fit window"


def aniki(s):
    """'Aniki' is used like a name; SH's 'Captain' is a title: vocative/after a determiner keep
    'Captain', elsewhere 'the Captain'."""
    def rep(m):
        pre = s[:m.start()]
        if re.search(r"(\b(our|the|my|your|their|his|dear|big|Our|The|My|Your|Their|His|Dear|Big)|[,:]) *$", pre):
            return "Captain"
        after = s[m.end():m.end() + 3]
        if re.match(r"(\x00|$|[!?,.~]|\.\.\.)", after) and not re.match(r"'s", after):
            if re.search(r"(^|[!?.~\x01] *)$", pre) or re.search(r"[!?~]", after[:1]) or after.startswith("..."):
                return "Captain"
        start = re.search(r"(^|[.!?~] |\x01|\.\.\. ?)$", pre) is not None
        return ("The Captain" if start else "the Captain")
    return re.sub(r"(?<![A-Za-z\-])Aniki(?![A-Za-z\-])", rep, s)


def term_fix(s, dialogue):
    reasons = []
    if dialogue and re.search(r"(?<![A-Za-z\-])Aniki(?![A-Za-z\-])", s):
        s = aniki(s); reasons.append("terminology Aniki->Captain (SH)")
    for bad, good in TERMS.items():
        if bad == "Aniki": continue
        if bad in NICK and not dialogue: continue
        rx = re.compile(r"(?<![A-Za-z\-])" + re.escape(bad) + r"(?![A-Za-z\-])")
        if rx.search(s):
            s = rx.sub(good, s); reasons.append(f"terminology {bad}->{good} (SH)")
    return s, reasons


def mech(s, fams, first_tag_is_dialogue):
    """s: text with tag placeholders. Returns (new, reasons)."""
    r = []
    dialogue = bool(set(fams) & DIALOGUE)
    n = re.sub(r"(?<=[^\s\x00\x01]) {2,3}(?=[^\s\x00])", " ", s)      # 4+ spaces = deliberate blank
    n = re.sub(r"(\x00C\d+\x01) {2,3}(?=[A-Za-z])", r"\1 ", n)   # "{/c}  was KO'd" -> SH single space
    if n != s: r.append("double space"); s = n
    n = re.sub(r"(?<=[A-Za-z]) +(?=[!?,;:](?!\.))", "", s)
    if n != s: r.append("space before punctuation"); s = n
    n = s
    if set(fams) & {"mN_N", "dramaN", "id_gallery", "id_gallery_r", "id_brief_r", "id_tenka", "id_tenka_r"}:
        n = re.sub(r"(?<=[^\s]) +(?=\x00[BP])", "", n)
    if dialogue: n = re.sub(r"(?<=[^\s]) +(?=\x00E)", "", n)
    if n != s: r.append("trailing space before break"); s = n
    s2, tr = term_fix(s, dialogue); s = s2; r += tr
    for bad, (good, why) in TYPOS.items():
        rx = re.compile(r"(?<![A-Za-z'])" + re.escape(bad) + r"(?![A-Za-z'])")
        if rx.search(s):
            s = rx.sub(good, s); r.append(why)
    n = re.sub(r"\b([Aa]) (hour|honou?r|honest|heir)", lambda m: m.group(1) + "n " + m.group(2), s)
    if n != s: r.append("a -> an"); s = n
    n = re.sub(r"(?<=[A-Za-z]) Have arrived!", " have arrived!", s)
    if n != s: r.append("capitalisation"); s = n
    return s, r


def final_punct(t):
    """Dialogue: add a full stop to speeches that end in a letter/digit (SH: 99.6% end punctuated)."""
    pieces = t.split("{p}")
    changed = False
    for k, piece in enumerate(pieces):
        m = re.match(r"^(.*?[A-Za-z0-9])((?:\{(?!br\})[^{}]*\})*)$", piece, re.S)
        if not m or not re.search(r"[A-Za-z]", re.sub(r"\{[^{}]*\}", "", piece)): continue
        body = re.sub(r"\{[^{}]*\}", "", m.group(1))
        nxt = re.sub(r"^(\{[^{}]*\})*", "", pieces[k + 1]) if k + 1 < len(pieces) else ""
        if nxt[:1].islower(): continue                          # continues into the next speech
        tail = body.split()[-1].lower() if body.split() else ""
        punct = "..." if tail in ("and", "but", "or", "the", "a", "to", "of", "if", "so") else "."
        pieces[k] = m.group(1) + punct + m.group(2); changed = True
    return "{p}".join(pieces), changed


def cap_speech_start(t):
    pieces = t.split("{p}")
    changed = False
    prev_end = "."
    for k, piece in enumerate(pieces):
        m = re.match(r"^((?:\{[^{}]*\})*)([a-z])", piece)
        vis = re.sub(r"\{[^{}]*\}", "", piece).strip()
        if m and prev_end in (".", "!", "?") and not re.match(r"^((?:\{[^{}]*\})*)(e\.g|i\.e|etc)", piece):
            pieces[k] = m.group(1) + m.group(2).upper() + piece[m.end():]; changed = True
        if vis: prev_end = "..." if vis.endswith("..") else vis[-1]
    return "{p}".join(pieces), changed


def main():
    rewrites = {}
    if (W / "rewrites.tsv").exists():
        for row in csv.DictReader(open(W / "rewrites.tsv", encoding="utf-8"), dialect="excel-tab"):
            rewrites[row["old"]] = (row["new"], row.get("reason") or "flow rewrite")
    props, rejected = {}, {}
    for t, x in F.items():
        if x["sh_verbatim"] or "{g:" in t or FC0E_INJ.search(t) or x["fc0e_only"] or any(c == "STRUCTURAL_DAMAGE" for c, _ in x["codes"]):
            continue
        fams = x["fams"]
        dialogue = bool(set(fams) & DIALOGUE) and t.startswith(("{FC17", "{FC16"))
        speech = t.startswith("{FC17")
        reasons = []
        new = textmap(t, lambda s: mech_wrap(s, fams, reasons))
        if speech and set(fams) <= DIALOGUE:
            n2, ch = final_punct(new)
            if ch: new = n2; reasons.append("sentence-final punctuation")
            n2, ch = cap_speech_start(new)
            if ch: new = n2; reasons.append("capitalise speech start")
        if t in rewrites:
            new, why = rewrites[t][0], rewrites[t][1]
            reasons = [why]
        codes = {c for c, _ in x["codes"]}
        if new == t and "WIDTH_OVERFLOW" not in codes and "TOO_MANY_LINES" not in codes:
            continue
        if placeables(new) != placeables(t):
            rejected[t] = {"new": new, "why": "placeables changed"}; continue
        fitted, note = fit(t, new, fams) if (dialogue or not set(fams) & DIALOGUE) else (new, "")
        if fitted is None:
            rejected[t] = {"new": new, "why": note, "reasons": reasons}; continue
        if note: reasons.append(note)
        if fitted != t:
            props[t] = {"new": fitted, "reasons": sorted(set(reasons)), "n": x["n"], "fams": fams}
    for t, (nw, why) in rewrites.items():   # rewrites for texts with no lint finding
        if t in props or t in F: continue
        props[t] = {"new": nw, "reasons": [why], "n": None, "fams": None}
    json.dump(props, open(W / "proposals.json", "w"), ensure_ascii=False, indent=0)
    json.dump(rejected, open(W / "rejected.json", "w"), ensure_ascii=False, indent=0)
    import collections
    c = collections.Counter(r for p in props.values() for r in p["reasons"])
    print(len(props), "proposals;", len(rejected), "rejected")
    for k, v in c.most_common(): print(f"  {v:6} {k}")


def mech_wrap(s, fams, reasons):
    n, r = mech(s, fams, False)
    reasons += r
    return n


if __name__ == "__main__":
    main()
