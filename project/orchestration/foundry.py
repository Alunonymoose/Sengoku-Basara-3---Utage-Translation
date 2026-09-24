#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
from diff_cmd import diff_command
from export_cmd import export_ownership_command
from query_cmd import bind_log_command,hazards_command,query_command,status_command,verify_command
from recipe_cmd import recipe_new_command,recipe_validate_command
from snapshot_cmd import snapshot_command
from visual_cmd import visual_compare_command

def build_parser():
    ap=argparse.ArgumentParser(prog="foundry",description="BASARA Foundry v0.2 orchestration"); sub=ap.add_subparsers(dest="command",required=True)
    s=sub.add_parser("snapshot",help="Hash/index exact current live tree into SQLite"); s.add_argument("root"); s.add_argument("--state-dir"); s.add_argument("--repo-root"); s.add_argument("--git-commit"); s.add_argument("--rpcs3-log"); s.add_argument("--force",action="store_true"); s.add_argument("--fail-on-parse-error",action="store_true"); s.set_defaults(func=snapshot_command)
    q=sub.add_parser("query",help="Query exact resource ownership/providers"); q.add_argument("snapshot"); q.add_argument("resource"); q.add_argument("--type-hash"); q.add_argument("--exact",action="store_true"); q.add_argument("--json",action="store_true"); q.set_defaults(func=query_command)
    v=sub.add_parser("verify",help="Verify live files still match a snapshot"); v.add_argument("snapshot"); v.add_argument("--root"); v.set_defaults(func=verify_command)
    bl=sub.add_parser("bind-log",help="Bind observed RPCS3 ARC load order"); bl.add_argument("snapshot"); bl.add_argument("rpcs3_log"); bl.add_argument("--repo-root"); bl.set_defaults(func=bind_log_command)
    hz=sub.add_parser("hazards",help="List divergent duplicate-provider identities"); hz.add_argument("snapshot"); hz.add_argument("--limit",type=int); hz.set_defaults(func=hazards_command)
    d=sub.add_parser("diff",help="Compare two snapshots"); d.add_argument("a"); d.add_argument("b"); d.set_defaults(func=diff_command)
    st=sub.add_parser("status",help="Summarize a snapshot"); st.add_argument("snapshot"); st.set_defaults(func=status_command)
    ex=sub.add_parser("export-ownership",help="Export snapshot DB in existing ownership/donor-matcher formats"); ex.add_argument("snapshot"); ex.add_argument("--out",required=True); ex.add_argument("--repo-root"); ex.set_defaults(func=export_ownership_command)
    rn=sub.add_parser("recipe-new",help="Create hash-bound patch recipe"); rn.add_argument("snapshot"); rn.add_argument("resource"); rn.add_argument("--type-hash",required=True); rn.add_argument("--recipe-id",required=True); rn.add_argument("--candidate"); rn.add_argument("--encoder"); rn.add_argument("--out",required=True); rn.set_defaults(func=recipe_new_command)
    rv=sub.add_parser("recipe-validate",help="Validate recipe approval/snapshot binding"); rv.add_argument("recipe"); rv.add_argument("--snapshot"); rv.add_argument("--require-candidate",action="store_true"); rv.set_defaults(func=recipe_validate_command)
    vc=sub.add_parser("visual-compare",help="Compare runtime screenshot against a golden baseline"); vc.add_argument("baseline"); vc.add_argument("candidate"); vc.add_argument("--mask"); vc.add_argument("--out-dir",required=True); vc.add_argument("--snapshot-id"); vc.add_argument("--pixel-threshold",type=int,default=8); vc.add_argument("--max-changed-ratio",type=float,default=0.0); vc.set_defaults(func=visual_compare_command)
    return ap

def main(argv=None):
    args=build_parser().parse_args(argv); return int(args.func(args))
if __name__=="__main__": raise SystemExit(main())
