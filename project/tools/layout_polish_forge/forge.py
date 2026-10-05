from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
PIPELINE=[
 "audit_layout_referenced_textures.py",
 "make_layout_custom_review.py",
 "quality_metric_audit.py",
 "layout_content_overflow_audit.py",
 "boundary_continuation_audit.py",
 "audit_provider_mismatches.py",
 "quality_sh_donor_audit.py",
 "partial_jpn_live_cell_audit_fast.py",
 "whole_jpn_exact_live_cell_audit.py",
 "audit_all_waza2_rows.py",
]
HEAVY=["batch_render_composed_layouts.py"]
def run(name):
    p=HERE/name
    print("\n=== "+name+" ===",flush=True)
    return subprocess.call([sys.executable,str(p)])
if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else "audit"
    if cmd=="audit":
        seq=PIPELINE
    elif cmd=="full":
        seq=HEAVY+PIPELINE
    elif cmd=="rowfit":
        seq=["audit_all_waza2_rows.py"]
    elif cmd in PIPELINE+HEAVY:
        seq=[cmd]
    else:
        print("Usage: forge.py audit|full|rowfit|<script>")
        raise SystemExit(2)
    for s in seq:
        rc=run(s)
        if rc: raise SystemExit(rc)
