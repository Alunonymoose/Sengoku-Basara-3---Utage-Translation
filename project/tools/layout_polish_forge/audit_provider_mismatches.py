
from pathlib import Path
import sqlite3,json,collections,csv

DB=Path(r"E:\Utage Patching New\.foundry\cache\foundry_graph.sqlite")
AUD=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa\LAYOUT_REFERENCED_TEXTURE_AUDIT.csv")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")
refs=list(csv.DictReader(open(AUD,encoding="utf-8-sig")))
ref_names={r["texture_name"].lower() for r in refs}

c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
rows=c.execute("""
select f.role,f.rel_path,r.member_index,r.name,r.raw_sha256,r.xet_width,r.xet_height
from resources r join files f on f.id=r.file_id
where r.kind='texture'
order by lower(r.name),f.role,lower(f.rel_path),r.member_index
""").fetchall()

by=collections.defaultdict(list)
for x in rows:
    name=x["name"].lower()
    if name in ref_names:
        by[name].append(dict(x))

findings=[]
for name,items in by.items():
    eng=[x for x in items if x["role"]=="ENG"]
    if len(eng)<2: continue
    hashes=collections.defaultdict(list)
    for x in eng:hashes[x["raw_sha256"]].append(x)
    if len(hashes)<2: continue

    sh=[x for x in items if x["role"]=="SH"]
    jp=[x for x in items if x["role"]=="JPN"]
    sh_hashes={x["raw_sha256"] for x in sh}
    jp_hashes={x["raw_sha256"] for x in jp}

    counts=sorted(((len(v),h) for h,v in hashes.items()),reverse=True)
    majority_h=counts[0][1]
    for h,owners in hashes.items():
        cls=[]
        if h==majority_h:cls.append("ENG_MAJORITY")
        if h in sh_hashes:cls.append("SH_EXACT")
        if h in jp_hashes:cls.append("JPN_EXACT")
        findings.append({
          "texture_name":name,
          "variant_sha256":h,
          "owner_count":len(owners),
          "classification":";".join(cls),
          "owners":owners,
          "eng_variant_count":len(hashes),
          "majority_sha256":majority_h,
          "sh_exact_available":bool(sh_hashes),
          "sh_hashes":sorted(sh_hashes),
          "jpn_hashes":sorted(jp_hashes)
        })

# Only names with at least one minority variant worth looking at.
sus=[]
for name in sorted({f["texture_name"] for f in findings}):
    arr=[f for f in findings if f["texture_name"]==name]
    if len(arr)<2:continue
    # prioritize when a SH exact variant exists or one variant dominates.
    maxowners=max(f["owner_count"] for f in arr)
    score=0
    if any("SH_EXACT" in f["classification"] for f in arr):score+=50
    if maxowners>=3:score+=20
    if len(arr)==2:score+=5
    sus.append({"texture_name":name,"score":score,"variants":arr})
sus.sort(key=lambda x:(-x["score"],x["texture_name"]))

(OUT/"LIVE_REFERENCED_PROVIDER_MISMATCHES.json").write_text(json.dumps(sus,indent=2),encoding="utf-8")
print(json.dumps({
 "referenced_names":len(ref_names),
 "mismatch_names":len(sus),
 "with_sh_exact":sum(any("SH_EXACT" in v["classification"] for v in s["variants"]) for s in sus),
 "top20":[{
   "score":s["score"],"texture_name":s["texture_name"],
   "variants":[{"owners":v["owner_count"],"class":v["classification"],
                "paths":[o["rel_path"] for o in v["owners"][:6]]} for v in s["variants"]]
 } for s in sus[:20]]
},indent=2))
