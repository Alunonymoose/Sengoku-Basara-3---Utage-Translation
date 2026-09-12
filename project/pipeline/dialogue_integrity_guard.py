#!/usr/bin/env python3
"""BASARA dialogue integrity guard.

Compares a patched Utage mission-message ARC against pristine Utage JP and,
when available, the official Samurai Heroes English counterpart.

The checker separates visible glyph payload from the high 16-bit control-token
envelope. It does NOT assume that English text should be byte-identical to JP
or SH. Instead it reports structural drift and control-envelope mutations that
are unsupported by either authoritative source.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, struct, sys, zlib
from dataclasses import dataclass
from pathlib import Path

ARC_MAGIC=b"\x00CRA"; GSM_MAGIC=b"\x00GSM"; FIM_MAGIC=b"\x00FIM"; QRTS_MAGIC=b"QRTS"

@dataclass
class Entry:
    index:int; name:str; type_hash:int; compressed_size:int; declared_raw:int; payload_offset:int; raw:bytes

class ArcError(RuntimeError): pass

def sha256(b:bytes)->str: return hashlib.sha256(b).hexdigest()

def read_arc(path:Path):
    data=path.read_bytes()
    if data[:4] != ARC_MAGIC: raise ArcError(f"{path}: not ARC v8 magic")
    ver,count=struct.unpack_from('>HH',data,4)
    if ver != 8: raise ArcError(f"{path}: unsupported ARC version {ver}")
    out=[]
    for i in range(count):
        o=8+i*80
        if o+80>len(data): raise ArcError(f"{path}: truncated entry table")
        name=data[o:o+64].split(b'\0',1)[0].decode('ascii','replace')
        th,cs,dr,po=struct.unpack_from('>IIII',data,o+64)
        blob=data[po:po+cs]
        try: raw=zlib.decompress(blob)
        except zlib.error: raw=blob
        out.append(Entry(i,name,th,cs,dr,po,raw))
    return {'path':str(path),'size':len(data),'sha256':sha256(data),'version':ver,'entries':out}

def choose_resource(arc, magic:bytes, secondary=False)->Entry:
    hits=[e for e in arc['entries'] if e.raw[:4]==magic]
    if magic in (GSM_MAGIC,FIM_MAGIC):
        primary=[e for e in hits if not e.name.endswith('_r')]
        second=[e for e in hits if e.name.endswith('_r')]
        hits=second if secondary else primary
    if not hits: raise ArcError(f"{arc['path']}: no {'secondary ' if secondary else ''}{magic!r} resource")
    return hits[0]

def parse_gsm(raw:bytes):
    if raw[:4]!=GSM_MAGIC: raise ArcError('bad GSM magic')
    if len(raw)<16: raise ArcError('truncated GSM')
    count=struct.unpack_from('>I',raw,12)[0]
    table_end=16+count*8
    if table_end>len(raw): raise ArcError(f'GSM table beyond payload: count={count}')
    pool=raw[table_end:]
    slots=[]
    for i in range(count):
        off,ln=struct.unpack_from('>II',raw,16+i*8)
        a,b=off*2,(off+ln)*2
        if b>len(pool): raise ArcError(f'GSM slot {i} beyond pool: off={off} len={ln}')
        payload=pool[a:b]
        toks=list(struct.unpack(f'>{ln}H',payload)) if ln else []
        slots.append({'index':i,'offset':off,'length':ln,'tokens':toks,'raw':payload})
    return {'count':count,'slots':slots}

def envelope(slot): return tuple(t for t in slot['tokens'] if t>=0xF000)
def fmt_env(env): return ' '.join(f'{x:04X}' for x in env)

def only_inserts(current, base, allowed=(0xFFFE,)):
    """True when current is base with only allowed tokens inserted.

    0xFFFE is a newline marker in earlier Sengoku BASARA MSG research and is
    also used by official Samurai Heroes English resources. Newline-only drift
    is formatting, not evidence of progression/control corruption.
    """
    if base is None: return False
    i=0
    for token in current:
        if i < len(base) and token == base[i]: i += 1
        elif token in allowed: continue
        else: return False
    return i == len(base)

def fim_header(raw:bytes):
    if raw[:4]!=FIM_MAGIC: return None
    n=min(len(raw)//4,16)
    return {'length':len(raw),'sha256':sha256(raw),'head_u32':[f'0x{x:08X}' for x in struct.unpack_from(f'>{n}I',raw,0)]}
def qrts_summary(arc):
    hits=[e for e in arc['entries'] if e.raw[:4]==QRTS_MAGIC or e.type_hash==0x167DBBFF]
    return [{'index':e.index,'name':e.name,'length':len(e.raw),'sha256':sha256(e.raw)} for e in hits]

def compare(args):
    cur=read_arc(Path(args.current)); jp=read_arc(Path(args.jp)); sh=read_arc(Path(args.sh)) if args.sh else None
    cg=parse_gsm(choose_resource(cur,GSM_MAGIC).raw); jg=parse_gsm(choose_resource(jp,GSM_MAGIC).raw)
    sg=parse_gsm(choose_resource(sh,GSM_MAGIC).raw) if sh else None
    rows=[]; counts={k:0 for k in ['BOTH','SH_ONLY','JP_ONLY','CUSTOM']}
    env_counts={k:0 for k in ['JP','SH_ONLY','FORMAT_ONLY','UNSUPPORTED']}
    low_current={s['index'] for s in cg['slots'] if s['length']<=6}
    low_jp={s['index'] for s in jg['slots'] if s['length']<=6}
    for i,c in enumerate(cg['slots']):
        j=jg['slots'][i] if i<jg['count'] else None; s=sg['slots'][i] if sg and i<sg['count'] else None
        eqj=bool(j and c['raw']==j['raw']); eqs=bool(s and c['raw']==s['raw'])
        if eqj and eqs: cls='BOTH'
        elif eqs: cls='SH_ONLY'
        elif eqj: cls='JP_ONLY'
        else: cls='CUSTOM'
        counts[cls]+=1
        ce=envelope(c); je=envelope(j) if j else None; se=envelope(s) if s else None
        if je is not None and ce==je: ecls='JP'
        elif se is not None and ce==se: ecls='SH_ONLY'
        elif only_inserts(ce, je) or only_inserts(ce, se): ecls='FORMAT_ONLY'
        else: ecls='UNSUPPORTED'
        env_counts[ecls]+=1
        rows.append({'index':i,'payload_class':cls,'control_class':ecls,'current_length':c['length'],
                     'jp_length':j['length'] if j else None,'sh_length':s['length'] if s else None,
                     'current_control':fmt_env(ce),'jp_control':fmt_env(je or ()), 'sh_control':fmt_env(se or ()),
                     'current_sha256':sha256(c['raw']),'jp_sha256':sha256(j['raw']) if j else None,'sh_sha256':sha256(s['raw']) if s else None})
    cf=choose_resource(cur,FIM_MAGIC).raw; jf=choose_resource(jp,FIM_MAGIC).raw
    sf=choose_resource(sh,FIM_MAGIC).raw if sh else None
    report={
      'schema':'basara-dialogue-integrity-guard/v1',
      'inputs':{'current':{k:v for k,v in cur.items() if k!='entries'},'jp':{k:v for k,v in jp.items() if k!='entries'},
                'sh':({k:v for k,v in sh.items() if k!='entries'} if sh else None)},
      'arc_entry_counts':{'current':len(cur['entries']),'jp':len(jp['entries']),'sh':len(sh['entries']) if sh else None},
      'primary_gsm_counts':{'current':cg['count'],'jp':jg['count'],'sh':sg['count'] if sg else None},
      'low_length_control_indices_le_6':{'current':len(low_current),'jp':len(low_jp),'same_index_set':low_current==low_jp,
                                         'lost_from_jp':sorted(low_jp-low_current),'gained_vs_jp':sorted(low_current-low_jp)},
      'payload_slot_classes':counts,
      'control_envelope_classes':env_counts,
      'unsupported_control_indices':[r['index'] for r in rows if r['control_class']=='UNSUPPORTED'],
      'fim':{'current':fim_header(cf),'jp':fim_header(jf),'sh':fim_header(sf) if sf else None,
             'current_equals_jp':cf==jf,'current_equals_sh':bool(sf is not None and cf==sf)},
      'voice_companion':None,
      'rows':rows
    }
    if args.current_msg and args.jp_msg:
        cm=read_arc(Path(args.current_msg)); jm=read_arc(Path(args.jp_msg))
        cqr=qrts_summary(cm); jqr=qrts_summary(jm)
        report['voice_companion']={'current':cqr,'jp':jqr,'same_qrts':bool(cqr and jqr and cqr[0]['sha256']==jqr[0]['sha256'])}
    failures=[]
    if cg['count']!=jg['count']: failures.append(f'primary GSM slot count current={cg["count"]} != pristine JP={jg["count"]}')
    if len(cur['entries'])!=len(jp['entries']): failures.append(f'ARC entry count current={len(cur["entries"])} != pristine JP={len(jp["entries"])}')
    if low_current!=low_jp: failures.append('low-length/control slot index set drifted from pristine JP')
    if env_counts['UNSUPPORTED'] and not args.allow_unjustified_control: failures.append(f'{env_counts["UNSUPPORTED"]} control envelopes contain non-format mutations unsupported by pristine JP or official SH')
    if report['voice_companion'] and not report['voice_companion']['same_qrts']: failures.append('voice QRTS companion differs from pristine JP')
    report['status']='FAIL' if failures else 'PASS'; report['failures']=failures
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--current',required=True); ap.add_argument('--jp',required=True); ap.add_argument('--sh')
    ap.add_argument('--current-msg'); ap.add_argument('--jp-msg')
    ap.add_argument('--json'); ap.add_argument('--csv'); ap.add_argument('--allow-unjustified-control',action='store_true')
    a=ap.parse_args()
    try: r=compare(a)
    except (ArcError,OSError,struct.error) as e:
        print(f'ERROR: {e}',file=sys.stderr); return 2
    if a.json: Path(a.json).write_text(json.dumps(r,indent=2),encoding='utf-8')
    if a.csv:
        with open(a.csv,'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(r['rows'][0].keys()) if r['rows'] else ['index']); w.writeheader(); w.writerows(r['rows'])
    print(json.dumps({k:r[k] for k in ['status','arc_entry_counts','primary_gsm_counts','low_length_control_indices_le_6','payload_slot_classes','control_envelope_classes','voice_companion','failures']},indent=2))
    return 1 if r['status']=='FAIL' else 0
if __name__=='__main__': raise SystemExit(main())
