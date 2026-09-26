"""Which grammar do Capcom-authored (JPN / official SH) tables containing FF92/FF91 satisfy?"""
import sys, collections
from common import *
from basara.msg import Gsm, Fim, check
tree = sys.argv[1]
st = collections.Counter(); ex = {}
for (arc, name, kind), f in sorted(FILES[tree].items()):
    if kind != "gsm" or SKIP.search(arc): continue
    ff = FILES[tree].get((arc, name, "fim"))
    if not ff: continue
    g = Gsm.parse(read(f))
    if 0xFF92 not in g.pool: continue
    fim = Fim.parse(read(ff))
    w, l = check(g, fim, "western").ok, check(g, fim, "legacy").ok
    k = ("W" if w else "-") + ("L" if l else "-"); st[k] += 1; ex.setdefault(k, (arc, name))
print(tree, dict(st), ex)
