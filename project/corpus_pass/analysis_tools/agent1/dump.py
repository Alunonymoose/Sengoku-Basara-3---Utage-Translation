"""Dump records of one table from a tree: python dump.py tree arc name [rec...]"""
import sys
from common import *
from basara.msg import Gsm, Fim, WESTERN
from basara.markup import decode
tree, arc, name = sys.argv[1:4]; recs = [int(x) for x in sys.argv[4:]]
g = Gsm.parse(read(FILES[tree][(arc, name, "gsm")])); ff = FILES[tree].get((arc, name, "fim"))
fim = Fim.parse(read(ff)) if ff else None
cs = csa_for(tree, arc); csa = cs[0] if cs else None
print(len(g), "records", "fim primary", len(fim.primary) if fim else None, "sec", len(fim.secondary) if fim else None)
for r in recs or range(len(g)):
    w = g.words(r)
    try: t = decode(w, csa)
    except Exception as e: t = "ERR " + str(e) + " " + " ".join(f"{x:04X}" for x in w)
    fr = ""
    if fim:
        p = fim.primary[r]; n = p[3] >> 16
        fr = " prim=" + ",".join(f"{x:X}" for x in p) + " sec=" + ";".join(f"{fim.secondary[p[4]+k][0]:X}/{fim.secondary[p[4]+k][1]>>16:X}" for k in range(n))
    print(r, fr, "|", t)
