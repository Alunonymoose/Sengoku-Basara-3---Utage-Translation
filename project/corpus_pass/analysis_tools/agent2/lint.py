"""Automated polish lint over every live utage_eng record (deduplicated by markup).

    python lint.py <work dir with eng.jsonl, sh.jsonl, vocab.json> <fc0e_damage.tsv>
-> findings.json  {text: {"codes": [[code, detail]...], "n": instances, "fams": [...], "fc0e_only": bool}}
-> lint_counts.json
Width uses per-speech measurement (widths.py) against the SH-derived window budgets below.
"""
import collections, csv, json, re, sys
from pathlib import Path
from spellchecker import SpellChecker
import corpus as C
from norm import speeches, WORD, TAG
from widths import speech_widths
from basara.font import Tnf, Csa
from basara.markup import encode

W = Path(sys.argv[1])
FC0E = set()
for row in csv.DictReader(open(sys.argv[2], encoding="utf-8"), dialect="excel-tab"):
    FC0E.add((row["arc"], row["table"], int(row["record"])))

# Budgets: max line width of official SH English in the same table family (per-speech measurement,
# same ascii TNF). Dialogue: SH mission dialogue max 566, drama 552, captions 667.
BUDGET = {"mN_N": 566, "mN_N_r": 527, "dramaN": 552, "caption": 667, "caption_evs": 667, "caption_evsN": 667,
          "id_brief_r": 587, "id_gallery": 443, "id_gallery_r": 613, "id_result": 422, "id_tenka_r": 423,
          "id_option": 651, "id_pause": 378, "id_otomo_skill_r": 188, "id_versus_r": 351}
MAXLINES = {"mN_N": 3, "dramaN": 3}

def fam(table):
    return re.sub(r"\d+", "N", table.split("\\")[-1])

D = SpellChecker().word_frequency.dictionary
V = json.loads((W / "vocab.json").read_text())
SHV = set(w.lower() for w in V["S"])
EXTRA_OK = set((W / "whitelist.txt").read_text().split()) if (W / "whitelist.txt").exists() else set()

def british_ok(l):
    for a, b in (("our", "or"), ("ise", "ize"), ("ised", "ized"), ("ising", "izing"), ("isation", "ization"),
                 ("yse", "yze"), ("ysed", "yzed"), ("tre", "ter"), ("bre", "ber"), ("lled", "led"), ("lling", "ling"),
                 ("ours", "ors"), ("oured", "ored"), ("ouring", "oring"), ("ourite", "orite"), ("ourable", "orable"),
                 ("ogue", "og"), ("ence", "ense"), ("ller", "ler"), ("ises", "izes")):
        if a in l:
            for m in re.finditer(a, l):
                c = l[:m.start()] + b + l[m.end():]
                if c in D: return True
    return l in ("grey", "draught", "draughts", "whilst", "amongst", "learnt", "burnt", "spelt", "dreamt", "cheque",
                 "gaol", "plough", "sceptre", "moustache", "storey", "tyre", "kerb", "manoeuvre", "queueing",
                 "judgement", "ageing", "programme", "annexe", "speciality", "mould", "mouldering", "smoulder")

def interj(w):
    l = w.lower()
    return bool(re.search(r"(.)\1\1", l) or
                re.fullmatch(r"[a-z]{0,3}?(ha|he|hi|ho|hu|fu|ku|hya|ga|gu|nu|wa|fo|mu|ah|eh|oh|uh|u){2,}[a-z]{0,2}", l)
                or re.fullmatch(r"(h+m+|m+h*|n+g*h+|u+r*g+h+|a+r*g+h+|g+a*h+|t+c*h+|p+s*h+t*|s+h+|z+|e+r+m+|h+u+h+|o+h+)", l))

def known(w):
    l = w.lower().replace("'s", "") if w.lower().endswith("'s") else w.lower()
    return (l in D or l in SHV or w in SHV or l in EXTRA_OK or british_ok(l) or interj(l)
            or (l.endswith("s") and (l[:-1] in D or l[:-1] in SHV)) or l.isdigit())

TERMS = json.loads((W / "terms.json").read_text()) if (W / "terms.json").exists() else {}
TERM_RX = [(re.compile(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])"), k, v) for k, v in TERMS.items()]
# control-code damage owned by the FIM/FC0E repair work (not edited here): FC17 whose 3rd argument is not
# FFFF (args overwritten, letters injected) and FC0E followed directly by glyphs.
STRUCT = re.compile(r"\{FC17:[0-9A-F]+,[0-9A-F]+,(?!FFFF\})[^}]*\}|\{FC17:[0-9A-F]+,[0-9A-F]+\}|\{FC0E:[^}]*\}[^{]")
GARBLE = re.compile(r"\b[b-df-hj-np-tv-xz]{5,}\b", re.I)
AN_EXC = re.compile(r"^(hour|honou?r|honest|heir|herb)", re.I)
A_EXC = re.compile(r"^(one|once|uni|use|usu|uto|eu|ewe|u[bcfgklmrst][aeiou]|ur[aeiou])", re.I)

def check(t, fams, tnf, csa):
    out = []
    if STRUCT.search(t):
        out.append(("STRUCTURAL_DAMAGE", STRUCT.search(t).group(0)))
    if "{g:" in t:
        out.append(("UNDECODABLE_GLYPHS", "text uses glyphs outside this font's CSA"))
        return out
    sps = speeches(t)
    raw_lines = [l for sp in sps for l in sp]
    joined = [" ".join(x.strip() for x in sp) for sp in sps]
    for s in joined:
        if re.search(r"\?\?\?|TODO|TBD|XXX|placeholder|dummy", s, re.I) and s.strip() != "???":
            out.append(("PLACEHOLDER", s[:80]))
        elif s.strip() == "???":
            out.append(("PLACEHOLDER_LOCKED", "???"))
        for g in GARBLE.findall(s):
            if not interj(g) and g.lower() not in ("hmm", "hmph", "psst", "shh", "tsk", "brr", "grr", "nth"):
                out.append(("GARBLED", g))
        if re.search(r"[^\x00-\x7f’‘“”…—–]", s):
            out.append(("NON_ASCII", s[:60]))
    # whitespace / punctuation (on markup, so {br}/{p} positions count)
    body = TAG.sub(lambda m: m.group(0) if m.group(0) in ("{br}", "{p}", "{end}") else "", t)
    if re.search(r"[^ ] {2,}[^ ]", body): out.append(("DOUBLE_SPACE", re.search(r".{0,15} {2,}.{0,15}", body).group(0)))
    if re.search(r" (\{br\}|\{p\}|\{end\})", body): out.append(("TRAILING_SPACE", ""))
    if re.search(r"(\{br\}|\{p\}|^) +\S", body): out.append(("LEADING_SPACE", ""))
    for s in joined:
        for m in re.finditer(r"\w [,.!?;:](?!\.\.)", s):
            out.append(("SPACE_BEFORE_PUNCT", s[max(0, m.start() - 12):m.end() + 12]))
        for m in re.finditer(r"[a-z][,;:][A-Za-z]|[a-z]{2}[.!?][A-Z][a-z]", s):
            if not re.search(r"(Lv|No|Mr|Mrs|Dr|St|vs|etc|e\.g|i\.e)\.", s[max(0, m.start() - 3):m.end()]):
                out.append(("MISSING_SPACE_AFTER_PUNCT", s[max(0, m.start() - 12):m.end() + 12]))
        for m in re.finditer(r"(?<!\.)\.\.(?!\.)|,,|[!?],|,[.!?]|\.,|;[.,]|\.!|\.\?(?!!)", s):
            out.append(("ODD_PUNCT", s[max(0, m.start() - 12):m.end() + 12]))
        if s.count('"') % 2: out.append(("UNBALANCED_QUOTES", s[:80]))
        if s.count("(") != s.count(")"): out.append(("UNBALANCED_PARENS", s[:80]))
        if re.search(r"(^|[.!?] )[a-z]", s) and not re.match(r"^\.\.\.", s):
            m = re.search(r"(^|(?<!\.)[.!?] )[a-z]\w*", s)
            if m and not re.match(r"(?:^| )?(e\.g|i\.e)", m.group(0)):
                out.append(("LOWERCASE_SENTENCE_START", s[max(0, m.start() - 10):m.end() + 10]))
        if re.search(r"(?<![A-Za-z'])i(?![A-Za-z'])(?!\.)", s): out.append(("LOWERCASE_I", s[:80]))
        for m in re.finditer(r"\b([A-Za-z]+) \1\b", s, re.I):
            out.append(("DOUBLED_WORD", s[max(0, m.start() - 12):m.end() + 12]))
        for m in re.finditer(r"\b([Aa]n?) ([A-Za-z]+)", s):
            art, nxt = m.group(1).lower(), m.group(2)
            if art == "a" and re.match(r"[aeiou]", nxt, re.I) and not A_EXC.match(nxt) and nxt.upper() != nxt:
                out.append(("ARTICLE_A_AN", m.group(0)))
            if art == "an" and re.match(r"[b-df-hj-np-tv-z]", nxt, re.I) and not AN_EXC.match(nxt) and nxt.upper() != nxt:
                out.append(("ARTICLE_A_AN", m.group(0)))
        for m in re.finditer(r"\b(he|she|it) (have|are|were|do|don't)\b|\b(I) (is|are|was not|has)\b|\b(you|we|they) (is|was|has|does|doesn't|wasn't)\b|\b(there) (is|was) (many|several|two|three|few)\b", s, re.I):
            out.append(("SUBJECT_VERB", m.group(0)))
        if any(f in ("mN_N", "dramaN") for f in fams) and re.search(r"[A-Za-z0-9]$", s.strip()):
            out.append(("NO_FINAL_PUNCT", s[-40:]))
        for rx, bad, good in TERM_RX:
            if rx.search(s): out.append(("TERMINOLOGY", f"{bad} -> {good}"))
        for w in WORD.findall(s):
            if not known(w): out.append(("SPELLING", w))
    # line breaks splitting words: letter{br}letter with no space and a joined dictionary word
    for m in re.finditer(r"([A-Za-z]+)\{br\}([a-z]+)", body):
        a, b = m.group(1), m.group(2)
        if known(a + b) and not (known(a) and known(b)):
            out.append(("BR_SPLITS_WORD", a + "|" + b))
    # widths
    try:
        sw = speech_widths(encode(t, csa), tnf)
    except Exception:
        sw = []
    for f in fams:
        b = BUDGET.get(f)
        if b and sw and max(max(sp) for sp in sw) > b:
            out.append(("WIDTH_OVERFLOW", f"{f}: {max(max(sp) for sp in sw)} > {b}"))
            break
    for f in fams:
        ml = MAXLINES.get(f)
        if ml and sw and max(len(sp) for sp in sw) > ml:
            out.append(("TOO_MANY_LINES", f"{f}: {max(len(sp) for sp in sw)} > {ml}"))
            break
    return out

if __name__ == "__main__":
    tnf = Tnf.parse((C.FONTS / "tnf/df843e0b42390e89.tnf").read_bytes())
    csa = Csa.parse((C.FONTS / "csa/9d5b493204cae29b.csa").read_bytes())
    inst = collections.defaultdict(lambda: {"n": 0, "fams": set(), "fc0e": 0, "font": set()})
    for l in open(W / "eng.jsonl", encoding="utf-8"):
        d = json.loads(l)
        x = inst[d["t"]]
        x["n"] += 1; x["fams"].add(fam(d["table"])); x["font"].add(d["font"])
        x["fc0e"] += (d["arc"], d["table"], d["r"]) in FC0E
    shplain = set()
    for l in open(W / "sh.jsonl", encoding="utf-8"):
        shplain.add(json.loads(l)["t"])
    res, counts_u, counts_i, ex = {}, collections.Counter(), collections.Counter(), collections.defaultdict(list)
    for t, x in inst.items():
        codes = check(t, x["fams"], tnf, csa)
        if not codes: continue
        fc0e_only = x["fc0e"] == x["n"]
        res[t] = {"codes": codes, "n": x["n"], "fams": sorted(x["fams"]), "fc0e_only": fc0e_only,
                  "fc0e": x["fc0e"], "sh_verbatim": t in shplain}
        for c in set(c for c, _ in codes):
            counts_u[c] += 1; counts_i[c] += x["n"]
            if len(ex[c]) < 8: ex[c].append([d for cc, d in codes if cc == c][0])
    json.dump(res, open(W / "findings.json", "w"), ensure_ascii=False)
    json.dump({"unique_texts": len(inst), "records": sum(x["n"] for x in inst.values()),
               "by_code_unique": counts_u, "by_code_records": counts_i, "examples": ex},
              open(W / "lint_counts.json", "w"), ensure_ascii=False, indent=1)
    for c, n in counts_u.most_common():
        print(f"{c:26} unique={n:6} records={counts_i[c]:8}  e.g. {ex[c][:3]}")
