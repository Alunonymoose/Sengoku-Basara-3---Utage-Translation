"""Near-match every unique Utage speech to official SH speeches; mine token substitutions
(terminology evidence) from pairs with high similarity."""
import json, collections, difflib, re, sys
from norm import speeches, WORD
def sp_lines(path):
    out = set()
    for l in open(path):
        for sp in speeches(json.loads(l)["t"]):
            s = re.sub(r"\s+", " ", " ".join(x.strip() for x in sp)).strip()
            if len(WORD.findall(s)) >= 3: out.add(s)
    return out
U = sp_lines("eng.jsonl"); S = sorted(sp_lines("sh.jsonl"))
df = collections.Counter(w.lower() for s in S for w in set(WORD.findall(s)))
inv = collections.defaultdict(list)
for i, s in enumerate(S):
    ws = sorted(set(w.lower() for w in WORD.findall(s)), key=lambda w: df[w])[:4]
    for w in ws: inv[w].append(i)
Sset = set(S)
pairs = []
for u in U:
    if u in Sset: continue
    ws = set(w.lower() for w in WORD.findall(u))
    cand = collections.Counter(i for w in ws for i in inv.get(w, ()) )
    best, br = None, 0
    for i, _ in cand.most_common(30):
        r = difflib.SequenceMatcher(None, u, S[i]).ratio()
        if r > br: best, br = S[i], r
    if br >= 0.75: pairs.append((u, best, round(br, 3)))
json.dump(pairs, open("sh_pairs.json", "w"), ensure_ascii=False, indent=0)
subs = collections.Counter()
for u, s, r in pairs:
    a, b = WORD.findall(u), WORD.findall(s)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "replace" and i2 - i1 <= 2 and j2 - j1 <= 2:
            subs[(" ".join(a[i1:i2]), " ".join(b[j1:j2]))] += 1
json.dump([[k[0], k[1], v] for k, v in subs.most_common()], open("sh_subs.json", "w"), ensure_ascii=False, indent=0)
print(len(U), len(S), "pairs", len(pairs))
for (x, y), v in subs.most_common(150): print(v, repr(x), "->", repr(y))
