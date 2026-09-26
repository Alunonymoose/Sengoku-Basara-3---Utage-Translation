"""Per-record control skeleton diff ENG vs JPN (same arc/name/record)."""
import sys, json, collections
from common import *
from basara.msg import Gsm, WESTERN, tokenize, MsgError
def skel(words):
    try: toks = tokenize(words, WESTERN)
    except MsgError as e: return ("ERR", str(e))
    return tuple((t.word, t.args) for t in toks if t.word >= 0xF000 or 0xD000 <= t.word <= 0xEFFF)
st = collections.Counter(); kinds = collections.Counter(); ex = collections.defaultdict(list)
for arc, name, g, f in live_tables():
    jf = FILES["utage_jpn"].get((arc, name, "gsm"))
    if not jf: st["no_jpn"] += 1; continue
    ge, gj = Gsm.parse(read(g)), Gsm.parse(read(jf))
    if len(ge) != len(gj): st["reccount_differs"] += 1; ex["reccount"].append((arc, name, len(ge), len(gj))); continue
    st["tables"] += 1
    for r in range(len(ge)):
        a, b = skel(ge.words(r)), skel(gj.words(r))
        st["records"] += 1
        if a == b: st["same"] += 1; continue
        if a and a[0] == "ERR": k = "ENG_ERR"
        elif b and b[0] == "ERR": k = "JPN_ERR"
        else:
            wa = [x[0] for x in a]; wb = [x[0] for x in b]
            if wa == wb:
                d = sorted({f"{x[0]:04X}" for x, y in zip(a, b) if x != y}); k = "ARGS:" + ",".join(d)
            else:
                ca, cb = collections.Counter(wa), collections.Counter(wb)
                k = "WORDS:+" + ",".join(f"{w:04X}x{n}" for w, n in sorted((ca - cb).items())) + " -" + ",".join(f"{w:04X}x{n}" for w, n in sorted((cb - ca).items()))
        kinds[k] += 1
        if len(ex[k]) < 5: ex[k].append((arc, name, r))
print(dict(st))
for k, n in kinds.most_common(60): print(n, k, ex[k][:2])
json.dump({"stats": st, "kinds": kinds, "ex": ex}, open(sys.argv[1], "w"), indent=0)
