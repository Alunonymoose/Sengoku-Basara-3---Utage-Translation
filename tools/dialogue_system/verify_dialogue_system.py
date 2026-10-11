#!/usr/bin/env python3
"""Verify a root-ready dialogue patch made by repair_dialogue_system.py."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
# Reuse the exact parser/auditor from the repair tool.
from repair_dialogue_system import parse_arc, unpack, choose_primary_pair, sha, audit_gsm

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--nativeps3',type=Path,required=True); ap.add_argument('--patch-root',type=Path,required=True); ap.add_argument('--manifest',type=Path)
    a=ap.parse_args(); eng=a.nativeps3/'rom'/'eng'/'id'; jpn=a.nativeps3/'rom'/'jpn'/'id'; patch=a.patch_root/'rom'/'eng'/'id'
    failures=[]; checked=[]
    if not patch.is_dir(): raise SystemExit(f'patch id folder missing: {patch}')
    for pp in sorted(patch.glob('msg_m*_pl*.arc')):
        src=eng/pp.name; pri=jpn/pp.name
        if not src.exists() or not pri.exists(): failures.append({'file':pp.name,'reason':'missing source/pristine'}); continue
        try:
            sa,oa,pa=parse_arc(src),parse_arc(pp),parse_arc(pri)
            sn,sge,sg,sfe,sf,sn1,sn2=choose_primary_pair(sa); on,oge,og,ofe,of,on1,on2=choose_primary_pair(oa); pn,pge,pg,pfe,pf,pn1,pn2=choose_primary_pair(pa)
            if (sn1,sn2)!=(on1,on2): raise ValueError('output FIM cardinality differs from source')
            source_raw={e.index:unpack(e) for e in sa.entries}
            bad=[e.name for e in oa.entries if e.index!=ofe.index and unpack(e)!=source_raw.get(e.index)]
            if bad: raise ValueError('non-FIM resources changed: '+', '.join(bad[:3]))
            ga=audit_gsm(og,pg)
            if not ga['strict_control_contract_ok']: raise ValueError('primary GSM control contract fails pristine')
            checked.append({'file':pp.name,'sha256':sha(oa.data),'non_fim_identical':True,'gsm_contract_ok':True})
        except Exception as exc: failures.append({'file':pp.name,'reason':f'{type(exc).__name__}: {exc}'})
    result={'checked':len(checked),'failures':failures,'failure_count':len(failures),'status':'PASS' if not failures else 'FAIL'}
    print(json.dumps(result,indent=2)); return 1 if failures else 0
if __name__=='__main__': raise SystemExit(main())
