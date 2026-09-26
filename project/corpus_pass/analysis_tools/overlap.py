"""Exact (normalised) overlap between every live Utage ENG line and every official SH ENG line."""
import json, re, collections, sys
from pathlib import Path
from basara.msg import Gsm, WESTERN, MsgError
from basara.font import Csa
from basara.markup import decode
m = json.load(open("MANIFEST.json"))
csa = Csa.parse(Path(next(f["path"] for f in m["files"] if f["tree"] == "utage_eng" and f["kind"] == "csa")).read_bytes())
BACKUP = re.compile(r"BACKUP|backup|Copy|PRE_", re.I)
def norm(t):
    t = re.sub(r"\{(?!br\}|p\})[^{}]*\}", "", t).replace("{br}", " ").replace("{p}", " ")
    return re.sub(r"\s+", " ", t).strip()
def lines(tree, prefix=""):
    out = collections.defaultdict(set)   # text -> {family}
    for f in m["files"]:
        if f["tree"] != tree or f["kind"] != "gsm" or not f["arc"].startswith(prefix) or BACKUP.search(f["arc"]): continue
        g = Gsm.parse(Path(f["path"]).read_bytes())
        fam = f["arc"][len(prefix):].split("/")[0]
        for r in range(len(g)):
            try: t = decode(g.words(r), csa)
            except Exception: continue
            for piece in re.split(r"\{p\}", t):
                n = norm(piece)
                if len(re.sub(r"[^A-Za-z]", "", n)) >= 3: out[n].add(fam)
    return out
U = lines("utage_eng"); S = lines("sh", "PS3_GAME/USRDIR/nativePS3/rom/eng/")
shared = set(U) & set(S)
print(f"distinct live Utage ENG lines: {len(U)}   distinct official SH ENG lines: {len(S)}")
print(f"Utage lines identical to an official SH line: {len(shared)}  ({100*len(shared)/len(U):.1f}%)")
print(f"official SH lines present verbatim in Utage: {100*len(shared)/len(S):.1f}%")
fam = collections.Counter(); famall = collections.Counter()
for t, fs in U.items():
    for f in fs:
        famall[f] += 1
        if t in shared: fam[f] += 1
for f, n in famall.most_common(12): print(f"  {f:28} {fam[f]:6}/{n:<6} {100*fam[f]/n:5.1f}% official-verbatim")
json.dump({"shared": sorted(shared)}, open("/tmp/claude-0/shared.json", "w"))
json.dump({"U": {k: sorted(v) for k, v in U.items()}, "S": {k: sorted(v) for k, v in S.items()}}, open("/tmp/claude-0/lines.json", "w"))
