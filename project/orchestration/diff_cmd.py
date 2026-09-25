from __future__ import annotations
import json
from db import connect_db
from resolver import resolve_snapshot

def diff_command(args)->int:
    a=connect_db(resolve_snapshot(args.a)); b=connect_db(resolve_snapshot(args.b)); am={r["path"]:dict(r) for r in a.execute("SELECT path,size,sha256,kind FROM files")}; bm={r["path"]:dict(r) for r in b.execute("SELECT path,size,sha256,kind FROM files")}; a.close(); b.close()
    added=sorted(set(bm)-set(am)); removed=sorted(set(am)-set(bm)); changed=sorted(p for p in set(am)&set(bm) if am[p]["sha256"]!=bm[p]["sha256"])
    print(json.dumps({"added":added,"removed":removed,"changed":[{"path":p,"before":am[p]["sha256"],"after":bm[p]["sha256"]} for p in changed]},indent=2)); return 0
