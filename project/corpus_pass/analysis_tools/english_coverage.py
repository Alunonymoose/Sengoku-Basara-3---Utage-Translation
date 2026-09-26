"""How much live Utage ENG text is still not English? Every table, every record, own CSA."""
import json, re, collections, csv, sys
from pathlib import Path
from basara.msg import Gsm, CONTROL_MIN, GLYPH_LIMIT
from basara.font import Csa
m = json.load(open("MANIFEST.json"))
SKIP = re.compile(r"BACKUP|backup|Copy|PRE_", re.I)
csa_of = {}
for f in m["files"]:
    if f["kind"] == "csa": csa_of.setdefault((f["tree"], f["arc"]), f["path"])
jpn = {(f["arc"], f["name"]): f["path"] for f in m["files"] if f["tree"] == "utage_jpn" and f["kind"] == "gsm"}
cache = {}
def inv(tree, arc):
    p = csa_of.get((tree, arc))
    if p not in cache: cache[p] = Csa.parse(Path(p).read_bytes()).inverse() if p else {0: " "}
    return cache[p]
def glyphs(words):
    i, out = 0, []
    # control args are skipped by length heuristic: count only words < GLYPH_LIMIT not preceded by a control's arg slots
    from basara.msg import WESTERN, tokenize, MsgError
    try:
        for t in tokenize(words, WESTERN):
            if t.word < GLYPH_LIMIT: out.append(t.word)
    except MsgError:
        out = [w for w in words if w < GLYPH_LIMIT]
    return out
cls = collections.Counter(); fam = collections.defaultdict(collections.Counter); rows = []
for f in m["files"]:
    if f["tree"] != "utage_eng" or f["kind"] != "gsm" or SKIP.search(f["arc"]): continue
    g = Gsm.parse(Path(f["path"]).read_bytes()); iv = inv("utage_eng", f["arc"])
    jp = Gsm.parse(Path(jpn[(f["arc"], f["name"])]).read_bytes()) if (f["arc"], f["name"]) in jpn else None
    family = f["arc"].split("/")[0] if "/" in f["arc"] else f["arc"]
    for r in range(len(g)):
        w = g.words(r); gl = glyphs(w)
        if not gl: c = "NO_TEXT"
        else:
            unm = [x for x in gl if x not in iv]
            same_jp = jp is not None and r < len(jp) and jp.words(r) == w
            if not unm: c = "ENGLISH"
            elif same_jp: c = "UNTRANSLATED_IDENTICAL_TO_JPN"
            elif len(unm) == len(gl): c = "ALL_UNMAPPED_GLYPHS"
            else: c = "MIXED_ENGLISH_AND_UNMAPPED"
        cls[c] += 1; fam[family][c] += 1
        if c not in ("NO_TEXT", "ENGLISH"):
            rows.append({"arc": f["arc"], "table": f["name"], "record": r, "class": c, "glyphs": len(gl),
                         "unmapped": len([x for x in gl if x not in iv]), "sample_unmapped": " ".join(f"{x:04X}" for x in [x for x in gl if x not in iv][:8])})
tot = sum(v for k, v in cls.items() if k != "NO_TEXT")
print("records with visible text:", tot)
for k, v in cls.most_common(): print(f"  {k:32} {v:8}  {100*v/max(tot,1):6.2f}%" if k != "NO_TEXT" else f"  {k:32} {v:8}")
print("\nnon-English by family:")
for fa, c in sorted(fam.items(), key=lambda x: -sum(v for k, v in x[1].items() if k not in ('NO_TEXT','ENGLISH'))):
    bad = sum(v for k, v in c.items() if k not in ("NO_TEXT", "ENGLISH"))
    if bad: print(f"  {fa:34} {bad:7} of {sum(v for k,v in c.items() if k!='NO_TEXT'):7}   {dict((k,v) for k,v in c.items() if k not in ('NO_TEXT','ENGLISH'))}")
with open(sys.argv[1], "w", newline="", encoding="utf-8") as fh:
    wr = csv.DictWriter(fh, fieldnames=["arc", "table", "record", "class", "glyphs", "unmapped", "sample_unmapped"], dialect="excel-tab"); wr.writeheader(); wr.writerows(rows)
