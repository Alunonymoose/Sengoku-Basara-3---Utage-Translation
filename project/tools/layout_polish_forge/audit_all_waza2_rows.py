from pathlib import Path
import sys,importlib.util,numpy as np,json,hashlib

sys.path.insert(0,r"E:\BASARA_AGENT_WORKTREES\gpt\project\Alrummi3")
from alrummi3_core import parse_arc,unpack_entry
XDIR=Path(r"E:\BASARA_AGENT_WORKTREES\gpt\project\texture_tools\xet_ps3_2026-09-25")
sys.path.insert(0,str(XDIR))
spec=importlib.util.spec_from_file_location("xet_ps3",str(XDIR/"xet_ps3.py"))
xet=importlib.util.module_from_spec(spec);spec.loader.exec_module(xet)

ENG=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng\select\c_versus.arc")
JPN=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn\select\c_versus.arc")
ea=parse_arc(ENG);ja=parse_arc(JPN);jb={e.name.lower():e for e in ja.entries}
rows=[]
for e in ea.entries:
    low=e.name.lower()
    if "waza2_" not in low or not low.endswith("_id_hq"):continue
    je=jb.get(low)
    if not je:continue
    er=xet.decode_display(unpack_entry(e));jr=xet.decode_display(unpack_entry(je))
    if er.shape!=(128,256,4) or jr.shape!=er.shape:continue
    em=er[...,3]>16;jm=jr[...,3]>16
    detail=[];bad_seams=0
    for boundary in (42,84):
        # Only the immediate seam matters. Rows may legitimately start 2+ px into the next cell.
        eng_seam=int(em[max(0,boundary-1):min(128,boundary+1),:].sum())
        jpn_seam=int(jm[max(0,boundary-1):min(128,boundary+1),:].sum())
        clear=(eng_seam==0)
        if not clear:bad_seams+=1
        detail.append({"boundary_y":boundary,"eng_seam_alpha_px":eng_seam,"jpn_seam_alpha_px":jpn_seam,"clear":clear})
    # Also report each cell's alpha bbox.
    cells=[]
    for ri,(y0,y1) in enumerate(((0,42),(42,84),(84,126)),1):
        m=em[y0:y1]
        ys,xs=np.where(m)
        bbox=None if not len(xs) else [int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
        cells.append({"row":ri,"bbox_in_cell":bbox})
    rows.append({
      "index":e.index,"name":e.name,"bad_seams":bad_seams,"pass":bad_seams==0,
      "seams":detail,"cells":cells,
      "eng_raw":hashlib.sha256(unpack_entry(e)).hexdigest(),
      "jpn_raw":hashlib.sha256(unpack_entry(je)).hexdigest()
    })
out=Path(r"E:\BASARA_WORK\jobs\20261005-az-texture-qa\VERSUS_WAZA2_ROW_AUDIT_V2.json")
out.write_text(json.dumps(rows,indent=2),encoding="utf-8")
print(json.dumps({"count":len(rows),"pass_count":sum(r["pass"] for r in rows),"rows":rows},indent=2))
