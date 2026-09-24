#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('matrix',type=Path)
    ns=ap.parse_args()
    data=json.loads(ns.matrix.read_text(encoding='utf-8'))
    candidate=data.get('candidate') or {}
    root_hash=candidate.get('live_root_sha256')
    eboot_hash=candidate.get('eboot_sha256')
    errors=[]; blockers=[]
    if not root_hash: errors.append('candidate.live_root_sha256 missing')
    if not eboot_hash: errors.append('candidate.eboot_sha256 missing')
    seen=set()
    for row in data.get('rows',[]):
        rid=row.get('id')
        if not rid: errors.append('row missing id'); continue
        if rid in seen: errors.append(f'duplicate row id: {rid}')
        seen.add(rid)
        status=row.get('final_status')
        if status!='PASS': blockers.append({'id':rid,'status':status or 'MISSING'})
        if status=='PASS':
            if not root_hash or row.get('build_root_sha256')!=root_hash:
                errors.append(f'{rid}: PASS is not bound to candidate live_root_sha256')
            evidence=(row.get('screenshot_or_video_evidence') or [])+(row.get('rpcs3_log_evidence') or [])
            if not evidence: errors.append(f'{rid}: PASS has no evidence reference')
    out={'schema':data.get('schema'),'rows':len(data.get('rows',[])),'errors':errors,'blockers':blockers,'release_ready':not errors and not blockers}
    print(json.dumps(out,indent=2))
    if errors: return 2
    if blockers: return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
