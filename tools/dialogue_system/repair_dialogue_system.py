#!/usr/bin/env python3
"""Sengoku BASARA 3 Utage — whole-dialogue structural repair.

Production-safe mode repairs only FIM secondary column-0 reveal budgets when
all ownership/cardinality/control invariants are proven against same-name
pristine Utage archives. It does NOT rewrite translated primary GSM text or
voice/event links. It also performs a strict primary-GSM contract audit so
archives with deeper structural drift are surfaced instead of silently patched.

Output is a root-ready patch tree containing only ARCs that actually changed.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, shutil, struct, sys, zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ARGC={0xFC0F:1,0xFC12:0,0xFC16:1,0xFC17:1,0xFED2:2,0xFF91:1,0xFF92:1,0xFFFA:1,0xFFFB:1,0xFFFD:0,0xFFFE:0,0xFFFF:0}
KNOWN_CTRL=set(ARGC)

@dataclass
class Entry:
    index:int; name:str; type_hash:int; comp_size:int; packed_size:int; raw_size:int; flags:int; offset:int; comp:bytes
@dataclass
class Arc:
    path:Path; data:bytes; entries:list[Entry]; first_payload:int; alignment:int

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def align(v:int,a:int)->int:return (v+a-1)//a*a

def parse_arc(path:Path)->Arc:
    data=path.read_bytes()
    if data[:4]!=b'\0CRA': raise ValueError('expected big-endian PS3 ARC (\\0CRA)')
    _version,count=struct.unpack_from('>HH',data,4)
    if len(data)<8+count*80: raise ValueError('truncated ARC table')
    entries=[]
    for i in range(count):
        ro=8+i*80; rec=data[ro:ro+80]
        name=rec[:64].split(b'\0',1)[0].decode('shift_jis','replace')
        th,cs,packed,off=struct.unpack_from('>IIII',rec,64)
        raw=packed>>3; flags=packed&7; comp=data[off:off+cs]
        if len(comp)!=cs: raise ValueError(f'entry {i} payload truncated')
        entries.append(Entry(i,name,th,cs,packed,raw,flags,off,comp))
    if not entries: raise ValueError('empty ARC')
    first=min(e.offset for e in entries)
    alignment=1
    for a in (32768,16384,8192,4096,2048,1024,512,256,128,64,32,16,8,4):
        if all(e.offset%a==0 for e in entries): alignment=a; break
    return Arc(path,data,entries,first,alignment)

def unpack(e:Entry)->bytes:
    try:return zlib.decompress(e.comp)
    except zlib.error:
        if e.comp_size==e.raw_size:return e.comp
        raise

def rebuild(arc:Arc,repl:dict[int,bytes])->bytes:
    out=bytearray(arc.data[:arc.first_payload]); payloads=[]; raws=[]
    for e in arc.entries:
        if e.index in repl:
            raw=repl[e.index]; payload=raw if e.comp_size==e.raw_size else zlib.compress(raw,9); rs=len(raw)
        else: payload=e.comp; rs=e.raw_size
        payloads.append(payload); raws.append(rs)
    cur=arc.first_payload; offsets=[]
    for p in payloads:
        cur=align(cur,arc.alignment)
        if len(out)<cur: out.extend(b'\0'*(cur-len(out)))
        offsets.append(cur); out.extend(p); cur+=len(p)
    for e,p,rs,off in zip(arc.entries,payloads,raws,offsets):
        ro=8+e.index*80
        struct.pack_into('>III',out,ro+64,e.type_hash,len(p),(rs<<3)|e.flags)
        struct.pack_into('>I',out,ro+76,off)
    return bytes(out)

def gsm_records(blob:bytes)->list[list[int]]:
    if blob[:4]!=b'\0GSM': raise ValueError('not GSM')
    pc,n=struct.unpack('>2I',blob[8:16]); pool=16+n*8
    if pool+pc*2!=len(blob): raise ValueError(f'bad GSM geometry: declared pool={pc}, rows={n}, bytes={len(blob)}')
    out=[]
    for i in range(n):
        off,l=struct.unpack('>2I',blob[16+i*8:24+i*8])
        if off+l>pc: raise ValueError(f'GSM row {i} exceeds pool')
        out.append(list(struct.unpack(f'>{l}H',blob[pool+off*2:pool+(off+l)*2])) if l else [])
    return out

def gsm_geometry(blob:bytes)->dict:
    pc,n=struct.unpack('>2I',blob[8:16]); rows=[]; used=0
    for i in range(n):
        off,l=struct.unpack('>2I',blob[16+i*8:24+i*8]); rows.append((off,l)); used=max(used,off+l)
    return {'pool_cells':pc,'rows':n,'used_cells':used,'trailing_pool_cells':max(0,pc-used),'table':rows}

def segments(seq:list[int]):
    out=[]; i=0
    while i<len(seq):
        x=seq[i]
        if x>=0xF000:
            argc=ARGC.get(x,1); n=1+argc
            if i+n>len(seq): out.append(('bad',[x],x)); break
            out.append(('c',seq[i:i+n],x)); i+=n
        elif x>=0x8000:
            out.append(('o',[x],None)); i+=1
        else:
            j=i
            while j<len(seq) and seq[j]<0x8000:j+=1
            out.append(('t',seq[i:j],None)); i=j
    return out

def dec_en(words:list[int])->str:
    s=[]
    for g in words:
        c=g+32 if g<6 else g+33
        s.append(chr(c) if 32<=c<=126 else '?')
    return ''.join(s)

def control_signature(seq:list[int], *, include_fffe:bool=True):
    sig=[]
    for kind,words,ctrl in segments(seq):
        if kind=='c':
            if include_fffe or ctrl!=0xFFFE: sig.append(tuple(words))
        elif kind=='bad': sig.append(tuple(words))
    return sig

def ctrl_count(seq:list[int],opcode:int)->int:
    return sum(1 for kind,_w,c in segments(seq) if kind=='c' and c==opcode)

def bucketize(seq:list[int],expected:int,english:bool):
    """Map a primary GSM record onto the FIM-owned secondary rows.

    FFFD terminates a real speech. FFFE is a line break. Styling controls do
    not create secondary ownership. A one-secondary system message with no
    FFFD owns all visible styled runs.
    """
    if expected<=0:return []
    buckets=[]; chars=0; lines=1; visible=False; text=[]; saw_end=False
    for kind,words,ctrl in segments(seq):
        if kind=='t':
            if english:
                rendered=dec_en(words); blank=not rendered.strip()
            else:
                blank=(not words) or all(w==0 for w in words)
            if not blank:
                chars+=len(words); visible=True
                if english:text.append(dec_en(words))
        elif kind=='o':
            pass
        elif ctrl==0xFFFE and visible:
            lines+=1
            if english:text.append('\\n')
        elif ctrl==0xFFFD:
            saw_end=True; buckets.append((chars,lines,''.join(text))); chars=0;lines=1;visible=False;text=[]
    if saw_end:
        return buckets if len(buckets)==expected else None
    if expected==1 and visible:return [(chars,lines,''.join(text))]
    if expected==1 and not visible:return []
    return None

def parts(arc:Arc):
    """Return FIM/GSM pairs keyed by ARC resource name."""
    by_name={}
    for e in arc.entries:
        raw=unpack(e); magic=raw[:4]
        if magic in (b'\0GSM',b'\0FIM'):
            by_name.setdefault(e.name,{})[magic]=(e,raw)
    return {n:v for n,v in by_name.items() if b'\0GSM' in v and b'\0FIM' in v}

def choose_primary_pair(arc:Arc):
    ps=parts(arc); candidates=[]
    for name,p in ps.items():
        ge,g=p[b'\0GSM']; fe,f=p[b'\0FIM']
        if len(f)<20: continue
        n1,n2,_=struct.unpack('>3I',f[8:20])
        try: gr=gsm_records(g)
        except Exception: continue
        if len(gr)!=n1: continue
        reverse=name.replace('\\','/').endswith('_r')
        candidates.append((reverse,-n1,name,ge,g,fe,f,n1,n2))
    if not candidates: raise ValueError('no coherent GSM/FIM primary pair')
    candidates.sort()
    return candidates[0][2:]

def primary_table(fim:bytes,n1:int)->list[tuple[int,int,int,int,int]]:
    need=32+n1*20
    if len(fim)<need: raise ValueError('FIM primary table truncated')
    return [struct.unpack('>5I',fim[32+i*20:52+i*20]) for i in range(n1)]

def audit_gsm(eng:bytes,jpn:bytes)->dict:
    er,jr=gsm_records(eng),gsm_records(jpn); eg,jg=gsm_geometry(eng),gsm_geometry(jpn)
    out={'eng_rows':len(er),'jpn_rows':len(jr),'row_count_match':len(er)==len(jr),
         'eng_pool_cells':eg['pool_cells'],'jpn_pool_cells':jg['pool_cells'],
         'eng_trailing_pool_cells':eg['trailing_pool_cells'],'jpn_trailing_pool_cells':jg['trailing_pool_cells'],
         'non_fffe_control_mismatch_rows':[],'fffd_count_mismatch_rows':[],
         'fffe_delta_rows':[],'length_outliers':[],'max_length_ratio':0.0}
    for i,(a,b) in enumerate(zip(er,jr)):
        if control_signature(a,include_fffe=False)!=control_signature(b,include_fffe=False):
            out['non_fffe_control_mismatch_rows'].append(i)
        if ctrl_count(a,0xFFFD)!=ctrl_count(b,0xFFFD): out['fffd_count_mismatch_rows'].append(i)
        da=ctrl_count(a,0xFFFE)-ctrl_count(b,0xFFFE)
        if da: out['fffe_delta_rows'].append({'row':i,'delta':da,'eng':ctrl_count(a,0xFFFE),'jpn':ctrl_count(b,0xFFFE)})
        if len(b):
            ratio=len(a)/len(b); out['max_length_ratio']=max(out['max_length_ratio'],ratio)
            if ratio>=3.0 and len(a)-len(b)>=24:
                out['length_outliers'].append({'row':i,'eng_cells':len(a),'jpn_cells':len(b),'ratio':round(ratio,3)})
        elif len(a): out['length_outliers'].append({'row':i,'eng_cells':len(a),'jpn_cells':0,'ratio':None})
    out['non_fffe_control_mismatch_count']=len(out['non_fffe_control_mismatch_rows'])
    out['fffd_count_mismatch_count']=len(out['fffd_count_mismatch_rows'])
    out['fffe_delta_count']=len(out['fffe_delta_rows'])
    out['length_outlier_count']=len(out['length_outliers'])
    out['strict_control_contract_ok']=out['row_count_match'] and not out['non_fffe_control_mismatch_rows'] and not out['fffd_count_mismatch_rows']
    return out

def repair_one(eng_path:Path,jpn_path:Path,out_path:Path|None)->dict:
    ta,pa=parse_arc(eng_path),parse_arc(jpn_path)
    tname,tge,tg,tfe,tf,tn1,tn2=choose_primary_pair(ta)
    pname,pge,pg,pfe,pf,pn1,pn2=choose_primary_pair(pa)
    report={'file':eng_path.name,'translated':str(eng_path),'pristine':str(jpn_path),
            'input_sha256':sha(ta.data),'pristine_sha256':sha(pa.data),'primary_resource':tname,
            'input_size':len(ta.data),'status':'AUDITED','changes':[],'skipped_rows':[]}
    report['gsm_audit']=audit_gsm(tg,pg)
    if (tn1,tn2)!=(pn1,pn2):
        report.update(status='BLOCKED_CARDINALITY_MISMATCH',eng_primary_rows=tn1,jpn_primary_rows=pn1,eng_secondary_rows=tn2,jpn_secondary_rows=pn2)
        return report
    tr,pr=gsm_records(tg),gsm_records(pg)
    if len(tr)!=tn1 or len(pr)!=pn1:
        report['status']='BLOCKED_GSM_FIM_ROW_MISMATCH'; return report
    tt,pt=primary_table(tf,tn1),primary_table(pf,pn1)
    if tt!=pt:
        diffs=[i for i,(a,b) in enumerate(zip(tt,pt)) if a!=b]
        report['status']='BLOCKED_PRIMARY_FIM_MISMATCH'; report['primary_fim_mismatch_rows']=diffs[:200]; report['primary_fim_mismatch_count']=len(diffs); return report
    if not report['gsm_audit']['strict_control_contract_ok']:
        report['status']='BLOCKED_PRIMARY_GSM_CONTROL_DRIFT'; return report
    ss=32+tn1*20; pss=32+pn1*20
    if len(tf)<ss+tn2*44 or len(pf)<pss+pn2*44:
        report['status']='BLOCKED_FIM_TRUNCATED'; return report
    newf=bytearray(tf); changes=[]; skipped=[]
    first=[r[4] for r in tt]
    if any(x>tn2 for x in first):
        report['status']='BLOCKED_FIM_OWNERSHIP_RANGE'; return report
    if any(first[i+1]<first[i] for i in range(len(first)-1)):
        report['status']='BLOCKED_FIM_OWNERSHIP_NONMONOTONIC'; return report
    for i in range(tn1-1):
        expected=first[i+1]-first[i]
        if expected<=0: continue
        eb=bucketize(tr[i],expected,True); pb=bucketize(pr[i],expected,False)
        if eb is None or pb is None:
            skipped.append({'row':i,'expected':expected,'reason':'speech-boundary ambiguity'}); continue
        if not eb or not pb: continue
        if len(eb)!=expected or len(pb)!=expected:
            skipped.append({'row':i,'expected':expected,'reason':'bucket cardinality mismatch'}); continue
        for j,((ec,el,txt),(pc,pl,_)) in enumerate(zip(eb,pb)):
            sec=first[i]+j; toff=ss+sec*44; poff=pss+sec*44
            old=struct.unpack_from('>I',tf,toff)[0]; pri=struct.unpack_from('>I',pf,poff)[0]
            slack=max(0,(pri&0xFFFF)-pc)
            old_lines,old_chars=old>>16,old&0xFFFF
            need_lines=el
            need_chars=min(0xFFFF,ec+slack)
            new_lines=max(old_lines,need_lines)
            new_chars=max(old_chars,need_chars)
            corrected=(new_lines<<16)|new_chars
            if corrected!=old:
                struct.pack_into('>I',newf,toff,corrected)
                changes.append({'primary_row':i,'secondary_row':sec,'old_lines':old_lines,'old_chars':old_chars,
                    'new_lines':new_lines,'new_chars':new_chars,'pristine_budget_lines':pri>>16,
                    'pristine_budget_chars':pri&0xFFFF,'pristine_visible_cells':pc,'preserved_slack':slack,
                    'english_visible_cells':ec,'english_text':txt})
    report['changes']=changes; report['change_count']=len(changes); report['skipped_rows']=skipped; report['skipped_count']=len(skipped)
    allowed=set()
    for c in changes:
        off=ss+c['secondary_row']*44; allowed.update(range(off,off+4))
    actual={i for i,(a,b) in enumerate(zip(tf,newf)) if a!=b}
    if not actual.issubset(allowed): raise AssertionError('repair escaped secondary col0')
    if not changes:
        report['status']='CLEAN_NO_CHANGE'; report['output_sha256']=report['input_sha256']; report['output_size']=len(ta.data); return report
    if out_path is None: raise ValueError('output path required when changes exist')
    built=rebuild(ta,{tfe.index:bytes(newf)})
    out_path.parent.mkdir(parents=True,exist_ok=True); out_path.write_bytes(built)
    oa=parse_arc(out_path); oname,oge,og,ofe,of,on1,on2=choose_primary_pair(oa)
    before={e.index:unpack(e) for e in ta.entries}; mism=[]
    for e in oa.entries:
        if e.index==ofe.index: continue
        if unpack(e)!=before[e.index]: mism.append({'index':e.index,'name':e.name})
    fim_escape=[i for i,(a,b) in enumerate(zip(tf,of)) if a!=b and i not in allowed]
    report['non_fim_raw_mismatches']=mism; report['fim_escape_bytes']=fim_escape[:100]
    report['all_non_fim_resources_raw_identical']=not mism
    report['only_permitted_fim_secondary_col0_changed']=not fim_escape
    report['output_sha256']=sha(built); report['output_size']=len(built); report['output_path']=str(out_path)
    report['status']='REPAIRED_STATICALLY_VERIFIED' if not mism and not fim_escape else 'FAILED_POST_VERIFY'
    return report

def discover(eng_dir:Path)->list[Path]:
    return sorted(p for p in eng_dir.glob('msg_m*_pl*.arc') if p.is_file())

def write_csv(reports:list[dict],path:Path):
    rows=[]
    for r in reports:
        if r.get('changes'):
            for c in r['changes']:
                rows.append({'file':r['file'],'status':r['status'],**{k:v for k,v in c.items() if k!='english_text'},'english_text':c.get('english_text','')})
        else: rows.append({'file':r.get('file',''),'status':r.get('status',''),'primary_row':'','secondary_row':'','old_lines':'','old_chars':'','new_lines':'','new_chars':'','english_text':''})
    fields=['file','status','primary_row','secondary_row','old_lines','old_chars','new_lines','new_chars','pristine_budget_lines','pristine_budget_chars','pristine_visible_cells','preserved_slack','english_visible_cells','english_text']
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description='Repair the entire current Utage translated dialogue corpus safely.')
    ap.add_argument('--nativeps3',type=Path,help='nativePS3 root containing rom/eng/id and rom/jpn/id')
    ap.add_argument('--eng-id',type=Path); ap.add_argument('--jpn-id',type=Path)
    ap.add_argument('--output',type=Path,required=True,help='output workspace; patch tree is written under ROOT_READY')
    ap.add_argument('--limit',type=int,default=0,help='development only: process first N files')
    a=ap.parse_args()
    if a.nativeps3:
        eng=a.nativeps3/'rom'/'eng'/'id'; jpn=a.nativeps3/'rom'/'jpn'/'id'
    else:
        if not a.eng_id or not a.jpn_id: ap.error('use --nativeps3 or both --eng-id and --jpn-id')
        eng,jpn=a.eng_id,a.jpn_id
    if not eng.is_dir(): raise SystemExit(f'English ID folder not found: {eng}')
    if not jpn.is_dir(): raise SystemExit(f'Pristine JPN ID folder not found: {jpn}')
    output=a.output.resolve(); patch=output/'ROOT_READY'/'rom'/'eng'/'id'; reports_dir=output/'reports'; reports_dir.mkdir(parents=True,exist_ok=True)
    inputs=discover(eng)
    if a.limit: inputs=inputs[:a.limit]
    reports=[]
    for idx,ep in enumerate(inputs,1):
        jp=jpn/ep.name
        print(f'[{idx}/{len(inputs)}] {ep.name}',flush=True)
        if not jp.exists():
            r={'file':ep.name,'translated':str(ep),'pristine':str(jp),'status':'BLOCKED_MISSING_PRISTINE','changes':[],'change_count':0}
        else:
            try:r=repair_one(ep,jp,patch/ep.name)
            except Exception as exc:r={'file':ep.name,'translated':str(ep),'pristine':str(jp),'status':'ERROR','error':f'{type(exc).__name__}: {exc}','changes':[],'change_count':0}
        reports.append(r)
        (reports_dir/f'{ep.stem}.json').write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
    statuses={}
    for r in reports: statuses[r['status']]=statuses.get(r['status'],0)+1
    summary={
        'tool':'UTAGE_DIALOGUE_SYSTEM_REPAIR','mode':'SAFE_FIM_BUDGET_REPAIR_PLUS_STRICT_GSM_AUDIT',
        'english_id':str(eng.resolve()),'pristine_id':str(jpn.resolve()),'files_scanned':len(reports),
        'files_repaired':sum(r.get('status')=='REPAIRED_STATICALLY_VERIFIED' for r in reports),
        'files_clean':sum(r.get('status')=='CLEAN_NO_CHANGE' for r in reports),
        'files_blocked_or_error':sum(r.get('status','').startswith(('BLOCKED_','ERROR','FAILED_')) for r in reports),
        'fim_cells_repaired':sum(r.get('change_count',0) for r in reports),
        'status_counts':statuses,
        'primary_gsm_control_drift_files':[r['file'] for r in reports if r.get('gsm_audit',{}).get('strict_control_contract_ok') is False],
        'cardinality_mismatch_files':[r['file'] for r in reports if r.get('status')=='BLOCKED_CARDINALITY_MISMATCH'],
        'ambiguous_fim_rows_total':sum(r.get('skipped_count',0) for r in reports),
        'runtime_status':'STATICALLY_VERIFIED_OUTPUTS; FULL GAME COLD-BOOT TEST STILL REQUIRED',
        'patch_root':str((output/'ROOT_READY').resolve()),
    }
    patch_zip=output/'UTAGE_DIALOGUE_ROOT_READY.zip'
    if patch_zip.exists(): patch_zip.unlink()
    shutil.make_archive(str(patch_zip.with_suffix('')), 'zip', root_dir=output/'ROOT_READY')
    summary['patch_zip']=str(patch_zip.resolve())
    (output/'manifest.json').write_text(json.dumps({'summary':summary,'files':reports},indent=2,ensure_ascii=False),encoding='utf-8')
    write_csv(reports,output/'changes.csv')
    (output/'SUMMARY.txt').write_text('\n'.join([f'{k}: {v}' for k,v in summary.items() if not isinstance(v,(list,dict))])+'\nstatus_counts: '+json.dumps(statuses,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)
    return 2 if summary['files_blocked_or_error'] else 0

if __name__=='__main__': raise SystemExit(main())
