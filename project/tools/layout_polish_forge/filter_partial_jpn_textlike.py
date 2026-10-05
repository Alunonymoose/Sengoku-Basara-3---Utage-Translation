from pathlib import Path
import json
root=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
rows=json.loads((root/"PARTIAL_JPN_LIVE_CELL_AUDIT_FAST.json").read_text(encoding="utf-8"))
terms=("text","title","name","page","system","detail","tassei","kotei","shuffle","rank","max","line","up04","clear","result","save","load","setting","option","record","history")
out=[]
for r in rows:
    w,h=r["crop_size"]
    a=w/max(h,1)
    n=r["node_name"].lower()
    textish=any(t in n for t in terms)
    shape=(w>=40 and h>=16 and w*h<=50000 and a>=1.3)
    if 0.02<=r["visible_coverage"]<=0.9 and (textish or shape):
        q=dict(r)
        q["filter_score"]=r["score"]+(40 if textish else 0)+(15 if r["default_visible"] else 0)
        out.append(q)
best={}
for r in out:
    k=(r["arc_path"],r["member_index"],tuple(r["rect"]))
    if k not in best or r["filter_score"]>best[k]["filter_score"]:
        best[k]=r
out=sorted(best.values(),key=lambda r:(-r["filter_score"],r["arc_path"].lower(),r["member_index"]))
(root/"PARTIAL_JPN_TEXTLIKE_CANDIDATES.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
print(json.dumps({"count":len(out),"top":out[:80]},indent=2))
