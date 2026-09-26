"""Contract census of every live ENG GSM/FIM pair: detect grammar, count violations under WESTERN."""
import sys, json, collections
from common import *
from basara.msg import Gsm, Fim, check, detect_grammar, MsgError
out = []; st = collections.Counter()
for arc, name, g, f in live_tables(sys.argv[1] if len(sys.argv) > 1 else "utage_eng"):
    if f is None: st["NO_FIM"] += 1; continue
    gsm, fim = Gsm.parse(read(g)), Fim.parse(read(f))
    row = {"arc": arc, "name": name}
    try:
        row["grammar"] = detect_grammar(gsm, fim); st["OK_" + row["grammar"]] += 1
    except MsgError as e:
        w = check(gsm, fim, "western"); l = check(gsm, fim, "legacy")
        row.update(status="UNCHARTED", w_viol=len(w.violations), w_err=w.errors[:1], l_viol=len(l.violations), l_err=l.errors[:1])
        st["UNCHARTED"] += 1
    out.append(row)
print(dict(st))
json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "census.json", "w"), indent=0)
for r in out:
    if r.get("status"): print(r)
