
from pathlib import Path
import sys,hashlib,json,csv,collections
sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
from layout import is_layout,parse_layout

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn")
SH=Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng")
OUT=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa")

def sha(b):return hashlib.sha256(b).hexdigest()
arc_cache={}
def get_arc(p):
    k=str(p)
    if k not in arc_cache:
        arc_cache[k]=parse_arc(p)
    return arc_cache[k]
def find_member(a,name):
    low=name.lower()
    hits=[e for e in a.entries if e.name.lower()==low]
    if not hits:
        # basename-ish fallback only for diagnostics, never donor proof
        hits=[e for e in a.entries if e.name.lower().endswith(low)]
    return hits[0] if len(hits)==1 else None

refs={}
layout_count=0
for p in sorted(ENG.rglob("*.arc"),key=lambda x:str(x.relative_to(ENG)).lower()):
    try:a=get_arc(p)
    except:continue
    rel=str(p.relative_to(ENG)).replace("\\","/")
    for e in a.entries:
        if e.type_hash!=0x60DD1B16 and not e.name.lower().endswith(".lsp"): continue
        try:
            raw=unpack_entry(e)
            if not is_layout(raw):continue
            lay=parse_layout(raw,e.name);layout_count+=1
        except:continue
        animated=set()
        for an in lay.animations:
            tgt=lay.animation_target(an)
            if tgt is not None:animated.add(tgt.index)
        for n in lay.nodes:
            if n.node_type not in (2,3) or not n.texture: continue
            key=(rel,n.texture.lower())
            r=refs.setdefault(key,{
                "arc_path":rel,"texture_name":n.texture,"consumers":[],
                "default_visible_count":0,"animated_consumer_count":0
            })
            r["consumers"].append({"layout":e.name,"node_index":n.index,"node_name":n.name,
                                   "default_display":bool(n.default_display),"animated":n.index in animated,
                                   "src":list(n.source_rect())})
            r["default_visible_count"]+=int(bool(n.default_display))
            r["animated_consumer_count"]+=int(n.index in animated)

rows=[]
errors=[]
for (rel,_),r in refs.items():
    ep=ENG/rel
    try:
        ea=get_arc(ep);ee=find_member(ea,r["texture_name"])
        if ee is None:
            errors.append({**r,"error":"ENG_MEMBER_NOT_FOUND"});continue
        eraw=unpack_entry(ee);eh=sha(eraw)
    except Exception as ex:
        errors.append({**r,"error":repr(ex)});continue

    jpn_state="NO_ARC";jh=None
    jp=JPN/rel
    if jp.exists():
        try:
            ja=get_arc(jp);je=find_member(ja,r["texture_name"])
            if je is None:jpn_state="NO_MEMBER"
            else:
                jh=sha(unpack_entry(je));jpn_state="EXACT" if jh==eh else "DIFF"
        except Exception as ex:jpn_state="ERROR"

    sh_state="NO_ARC";shh=None
    sp=SH/rel
    if sp.exists():
        try:
            sa=get_arc(sp);se=find_member(sa,r["texture_name"])
            if se is None:sh_state="NO_MEMBER"
            else:
                shh=sha(unpack_entry(se));sh_state="EXACT" if shh==eh else "DIFF"
        except Exception as ex:sh_state="ERROR"

    text=(rel+" "+r["texture_name"]).lower()
    ui_terms=["msg","name","title","menu","option","select","result","brief","tenka","kessen",
              "caption","text","rule","mission","quest","pause","save","retry","startup",
              "gallery","rank","join","player","battle","clear","mode","army","waza","item"]
    score=0;reasons=[]
    if jpn_state=="EXACT" and sh_state not in ("EXACT",):
        score+=40;reasons.append("LIVE_LAYOUT_JPN_EXACT_NO_SH_EXACT")
    if r["default_visible_count"]>0:
        score+=12;reasons.append("DEFAULT_VISIBLE")
    if r["animated_consumer_count"]>0:
        score+=8;reasons.append("ANIMATED")
    hits=[t for t in ui_terms if t in text]
    if hits:
        score+=min(20,4+2*len(hits));reasons.append("UI_TEXTISH")
    rows.append({
        "score":score,"arc_path":rel,"member_index":ee.index,"texture_name":ee.name,
        "eng_sha256":eh,"jpn_state":jpn_state,"sh_state":sh_state,
        "default_visible_count":r["default_visible_count"],
        "animated_consumer_count":r["animated_consumer_count"],
        "consumer_count":len(r["consumers"]),"reasons":";".join(reasons),
        "consumers":json.dumps(r["consumers"],ensure_ascii=False)
    })

rows.sort(key=lambda x:(-x["score"],x["arc_path"].lower(),x["member_index"]))
fields=[k for k in rows[0] if k!="consumers"]+["consumers"]
with (OUT/"LAYOUT_REFERENCED_TEXTURE_AUDIT.csv").open("w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
sus=[r for r in rows if r["jpn_state"]=="EXACT" and r["sh_state"]!="EXACT"]
(OUT/"LAYOUT_REFERENCED_JPN_EXACT_SUSPECTS.json").write_text(json.dumps(sus,indent=2),encoding="utf-8")
print(json.dumps({
    "layouts":layout_count,
    "unique_referenced_textures":len(rows),
    "lookup_errors":len(errors),
    "jpn_exact_no_sh_exact":len(sus),
    "default_visible_suspects":sum(r["default_visible_count"]>0 for r in sus),
    "top30":[{k:r[k] for k in ("score","arc_path","member_index","texture_name","jpn_state","sh_state","default_visible_count","animated_consumer_count","reasons")} for r in sus[:30]]
},indent=2))
