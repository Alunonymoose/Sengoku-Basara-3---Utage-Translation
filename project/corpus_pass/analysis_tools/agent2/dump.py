"""Dump every live utage_eng record (arc, table, record, markup, line widths) and every official
SH English record to JSONL for the lint pass."""
import json, sys, re, time
from pathlib import Path
import corpus as C
from basara.font import Csa
from basara.markup import decode
from basara.msg import Gsm, GRAMMARS, MsgError

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
with open(out / "eng.jsonl", "w", encoding="utf-8") as fh:
    for k, arc in enumerate(C.live_arcs()):
        for name in C.tables(arc):
            try:
                t = C.open_table(arc, name)
            except Exception as exc:
                print("SKIP", arc, name, exc); continue
            for r in range(len(t)):
                try:
                    txt = t.text(r)
                except Exception as exc:
                    txt = None
                if not txt or txt == "{end}":
                    continue
                m = t.width(r)
                fh.write(json.dumps({"arc": arc, "table": name, "r": r, "t": txt,
                                     "w": list(m.widths) if m else None, "g": t.grammar_name,
                                     "font": "ascii" if (t.csa and t.csa.ordinal("e") is not None) else "other"},
                                    ensure_ascii=False) + "\n")
        if k % 100 == 0: print(k, arc, round(time.time() - t0), flush=True)
# SH official English (decoded with the ascii CSA, as overlap.py does)
csa = Csa.parse(Path(C.FONTS / "csa/9d5b493204cae29b.csa").read_bytes())
with open(out / "sh.jsonl", "w", encoding="utf-8") as fh:
    for f in C.M:
        if f["tree"] != "sh" or f["kind"] != "gsm" or "/rom/eng/" not in f["arc"]: continue
        g = Gsm.parse((C.CORPUS / f["path"]).read_bytes())
        for r in range(len(g)):
            try: txt = decode(g.words(r), csa)
            except Exception: continue
            if txt and txt != "{end}":
                fh.write(json.dumps({"arc": f["arc"], "table": f["name"], "r": r, "t": txt}, ensure_ascii=False) + "\n")
print("done", round(time.time() - t0))
