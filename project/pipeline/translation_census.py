#!/usr/bin/env python3
"""Sengoku BASARA 3 Utage translation/provenance census.

This is deliberately conservative. It does not call an asset "translated"
merely because bytes differ from pristine Utage. It classifies provenance and
translation opportunity first, then leaves semantic completion as a separate
field.

Expected roots:
  --current <Utage live rom/eng>
  --jp      <pristine Utage rom/jpn>
  --sh      <official Samurai Heroes rom/eng>

Outputs JSON and CSV suitable for the BASARA Foundry evidence ledger.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, struct, sys, zlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

ARC_MAGIC=b"\x00CRA"; GSM=0x10C460E6; FIM=0x2EA515BF; XET=0x241F5DEB
MISSION_UTAGE=re.compile(r'^msg_m(\d{3})_pl(\d{3})\.arc$', re.I)
MISSION_SH=re.compile(r'^msg_pl(\d{3})_m(\d{3})\.arc$', re.I)

@dataclass
class ArcEntry:
    index:int; name:str; type_hash:int; raw_size:int; raw_sha256:str

@dataclass
class AssetRow:
    relative_path:str
    normalized_key:str
    kind:str
    state:str
    current_sha256:str
    jp_sha256:str|None
    sh_sha256:str|None
    current_size:int
    jp_size:int|None
    sh_size:int|None
    donor_eligible:bool
    donor_reason:str
    needs_art_review:bool
    notes:str

class ArcError(RuntimeError): pass

def sha256_bytes(b:bytes): return hashlib.sha256(b).hexdigest()
def sha256_file(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def read_arc(path:Path):
    data=path.read_bytes()
    if data[:4]!=ARC_MAGIC or len(data)<8: raise ArcError('not ARC v8')
    ver,count=struct.unpack_from('>HH',data,4)
    if ver!=8: raise ArcError(f'ARC version {ver}')
    entries=[]
    for i in range(count):
        o=8+i*80
        if o+80>len(data): raise ArcError('truncated entry table')
        name=data[o:o+64].split(b'\0',1)[0].decode('ascii','replace')
        th,cs,packed,po=struct.unpack_from('>IIII',data,o+64)
        blob=data[po:po+cs]
        try: raw=zlib.decompress(blob)
        except zlib.error: raw=blob
        entries.append(ArcEntry(i,name,th,len(raw),sha256_bytes(raw)))
    return entries

def normalize_rel(rel:Path)->str:
    s=rel.as_posix()
    name=rel.name
    m=MISSION_UTAGE.match(name)
    if m:
        stage,pl=m.groups(); return (rel.parent / f'msg_STAGE{stage}_PL{pl}.arc').as_posix().lower()
    m=MISSION_SH.match(name)
    if m:
        pl,stage=m.groups(); return (rel.parent / f'msg_STAGE{stage}_PL{pl}.arc').as_posix().lower()
    return s.lower()

def sh_candidates(rel:Path):
    out=[rel]
    m=MISSION_UTAGE.match(rel.name)
    if m:
        stage,pl=m.groups(); out.insert(0,rel.with_name(f'msg_pl{pl}_m{stage}.arc'))
    return out

def safe_arc_shape(path:Path):
    try:
        entries=read_arc(path)
        return [(e.name,e.type_hash,e.raw_size) for e in entries]
    except Exception: return None

def xet_header_shape(raw:bytes):
    # Keep intentionally generic: exact XET semantics vary. Header identity is
    # stronger evidence than guessed width/height parsing.
    return raw[:20] if len(raw)>=20 else raw

def direct_resource_provenance(cur:Path,jp:Optional[Path],sh:Optional[Path]):
    """Resource-level ARC summary used for stricter donor eligibility."""
    try: ce=read_arc(cur)
    except Exception: return None
    je={ (e.name,e.type_hash):e for e in read_arc(jp)} if jp and jp.exists() else {}
    se={ (e.name,e.type_hash):e for e in read_arc(sh)} if sh and sh.exists() else {}
    result=[]
    for e in ce:
        k=(e.name,e.type_hash); j=je.get(k); s=se.get(k)
        if s and e.raw_sha256==s.raw_sha256 and (not j or e.raw_sha256!=j.raw_sha256): state='DIRECT_OFFICIAL_TRANSPLANT'
        elif j and e.raw_sha256==j.raw_sha256: state='STOCK_OR_UNTRANSLATED'
        elif s and e.raw_sha256==s.raw_sha256: state='OFFICIAL_MATCH_SHARED'
        else: state='CUSTOM_MODIFIED'
        result.append({'index':e.index,'name':e.name,'type_hash':f'0x{e.type_hash:08X}','raw_size':e.raw_size,
                       'state':state,'jp_match':bool(j and e.raw_sha256==j.raw_sha256),
                       'sh_match':bool(s and e.raw_sha256==s.raw_sha256),'sh_same_key':bool(s)})
    return result

def classify(cur:Path,rel:Path,jp_root:Path,sh_root:Path):
    jp=jp_root/rel
    sh=None
    for cand in sh_candidates(rel):
        p=sh_root/cand
        if p.exists(): sh=p; break
    ch=sha256_file(cur); jh=sha256_file(jp) if jp.exists() else None; shh=sha256_file(sh) if sh else None
    kind='ARC' if cur.suffix.lower()=='.arc' else cur.suffix.lower().lstrip('.').upper() or 'FILE'
    if shh and ch==shh and (not jh or ch!=jh): state='DIRECT_OFFICIAL_TRANSPLANT'
    elif jh and ch==jh: state='STOCK_OR_UNTRANSLATED'
    elif shh and ch==shh: state='OFFICIAL_MATCH_SHARED'
    elif jp.exists(): state='CUSTOM_MODIFIED'
    else: state='CURRENT_ONLY'

    donor=False; reason=''
    if sh and state not in ('DIRECT_OFFICIAL_TRANSPLANT','OFFICIAL_MATCH_SHARED'):
        if cur.suffix.lower()=='.arc' and jp.exists():
            cshape=safe_arc_shape(cur); jshape=safe_arc_shape(jp); sshape=safe_arc_shape(sh)
            if cshape and jshape and sshape:
                # Whole-ARC direct donor is eligible only for exact Utage↔SH
                # structural shape. Resource-level donors may still exist even
                # when the archive is expanded in Utage.
                if jshape==sshape:
                    donor=True; reason='JP and SH ARC resource shape identical; official localization donor exists'
                else:
                    reason='SH counterpart exists but archive shape differs; resource-level/semantic transplant only'
            else: reason='counterpart exists; binary structure not parsed safely'
        else:
            donor=True; reason='official SH counterpart exists'
    elif not sh: reason='no same-path/mission-normalized official SH counterpart found'

    art=False
    notes=[]
    if cur.suffix.lower()=='.arc':
        rp=direct_resource_provenance(cur,jp if jp.exists() else None,sh)
        if rp:
            xets=[r for r in rp if r['type_hash']==f'0x{XET:08X}']
            custom_xets=[r for r in xets if r['state']=='CUSTOM_MODIFIED']
            if custom_xets:
                art=True; notes.append(f'{len(custom_xets)} custom-modified XET resource(s) require visual provenance/approval check')
            official=sum(r['state']=='DIRECT_OFFICIAL_TRANSPLANT' for r in rp)
            stock=sum(r['state']=='STOCK_OR_UNTRANSLATED' for r in rp)
            custom=sum(r['state']=='CUSTOM_MODIFIED' for r in rp)
            notes.append(f'resources: official={official}, stock={stock}, custom={custom}, total={len(rp)}')
    return AssetRow(rel.as_posix(),normalize_rel(rel),kind,state,ch,jh,shh,cur.stat().st_size,
                    jp.stat().st_size if jp.exists() else None,sh.stat().st_size if sh else None,
                    donor,reason,art,'; '.join(notes))

def walk_files(root:Path):
    for p in root.rglob('*'):
        if p.is_file() and not p.name.endswith('.audit.json'): yield p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--current',required=True); ap.add_argument('--jp',required=True); ap.add_argument('--sh',required=True)
    ap.add_argument('--json',required=True); ap.add_argument('--csv',required=True)
    a=ap.parse_args(); roots=[Path(a.current),Path(a.jp),Path(a.sh)]
    for r in roots:
        if not r.is_dir(): print(f'ERROR missing root: {r}',file=sys.stderr); return 2
    rows=[]
    for i,p in enumerate(walk_files(roots[0]),1):
        rel=p.relative_to(roots[0])
        try: rows.append(classify(p,rel,roots[1],roots[2]))
        except Exception as e:
            rows.append(AssetRow(rel.as_posix(),normalize_rel(rel),'ERROR','ERROR','',None,None,p.stat().st_size,None,None,False,'',False,str(e)))
        if i%250==0: print(f'processed {i} files...',file=sys.stderr)
    states={}; donor=art=0
    for r in rows:
        states[r.state]=states.get(r.state,0)+1; donor+=r.donor_eligible; art+=r.needs_art_review
    summary={'schema':'basara-translation-census/v1','roots':{'current':str(roots[0]),'jp':str(roots[1]),'sh':str(roots[2])},
             'file_count':len(rows),'states':states,'eligible_whole_asset_donors':donor,'custom_art_review_assets':art,
             'important':'STOCK_OR_UNTRANSLATED is provenance, not proof the visible content is Japanese. CUSTOM_MODIFIED is not automatically translated. Resource/semantic census must refine both.'}
    Path(a.json).write_text(json.dumps({'summary':summary,'assets':[asdict(r) for r in rows]},indent=2),encoding='utf-8')
    with open(a.csv,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(asdict(rows[0]).keys()) if rows else [f.name]); w.writeheader(); w.writerows(asdict(r) for r in rows)
    print(json.dumps(summary,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
