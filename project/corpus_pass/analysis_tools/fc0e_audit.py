"""FC0E reference audit: live ENG vs JPN original, record by record."""
import json, collections, csv, sys
from pathlib import Path
from basara.msg import Gsm
from basara.font import Csa
from basara.markup import decode
m = json.load(open("MANIFEST.json"))
idx = collections.defaultdict(dict)
for f in m["files"]:
    if f["kind"] == "gsm": idx[f["tree"]][(f["arc"], f["name"])] = f["path"]
csa = Csa.parse(Path(next(f["path"] for f in m["files"] if f["tree"] == "utage_eng" and f["kind"] == "csa")).read_bytes())
def fc0e(words):
    out = []
    for i, w in enumerate(words):
        if w == 0xFC0E and i + 2 < len(words):
            j = k = i + 3
            while k < len(words) and words[k] < 0xF000: k += 1
            out.append((words[i + 1], words[i + 2], tuple(words[j:k])))
    return out
st = collections.Counter(); rows = []; arcs = collections.Counter(); words_seen = collections.Counter()
for key, path in idx["utage_eng"].items():
    if "BACKUP" in key[0] or key not in idx["utage_jpn"]: continue
    ge, gj = Gsm.parse(Path(path).read_bytes()), Gsm.parse(Path(idx["utage_jpn"][key]).read_bytes())
    for r in range(min(len(ge), len(gj))):
        e, j = fc0e(ge.words(r)), fc0e(gj.words(r))
        if not e: continue
        st["records_with_FC0E"] += 1
        if len(e) != len(j): st["fc0e_count_differs_from_jpn"] += 1; continue
        bad = [(a, b) for a, b in zip(e, j) if a[2] or a[1] != b[1]]
        if not bad: st["clean"] += 1; continue
        st["records_damaged"] += 1; st["fc0e_damaged"] += len(bad); arcs[key[0]] += 1
        for a, b in bad:
            word = (decode([a[1]], csa).strip("{}") if a[1] < 0x8000 else "") + decode(list(a[2]), csa)
            words_seen[word] += 1
        if len(rows) < 20000:
            rows.append({"arc": key[0], "table": key[1], "record": r, "eng_fc0e": ";".join(f"{x[0]:X},{x[1]:X}+{len(x[2])}w" for x, _ in bad),
                         "jpn_fc0e": ";".join(f"{y[0]:X},{y[1]:X}" for _, y in bad), "eng_text": decode(ge.words(r), csa)[:300]})
print(dict(st)); print("archives affected:", len(arcs))
print("injected words (top):", words_seen.most_common(25))
with open(sys.argv[1], "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]), dialect="excel-tab"); w.writeheader(); w.writerows(rows)
