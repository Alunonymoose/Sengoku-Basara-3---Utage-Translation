from pathlib import Path
import hashlib,json,re,struct,sys,zlib
TOOLS=Path(r'E:\Utage Patching New\_codex_tenka_v6')
sys.path.insert(0,str(TOOLS))
import lsp_named_probe

OUT=Path(__file__).parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng')
quest=re.compile(r'(?:^|\\)quest_\d{3}_id_hq$',re.I)
def parse_lsp(raw):
    count=struct.unpack_from('>H',raw,12)[0]
    cursor=raw.find(b'\0\0\0\x08SysRoot\0',16+176*count)
    if cursor<0: raise ValueError('Missing SysRoot')
    nodes=[]
    for i in range(count):
        strings=[]
        for _ in range(2):
            ln=struct.unpack_from('>I',raw,cursor)[0]
            if ln<1 or cursor+4+ln>len(raw): raise ValueError(f'Bad string at {cursor:x}')
            strings.append(raw[cursor+4:cursor+3+ln].decode('latin-1'))
            cursor+=4+ln
        record=raw[16+i*176:16+(i+1)*176]
        words=lambda offsets:[struct.unpack_from('>i',record,o)[0] for o in offsets]
        floats=lambda offsets:[struct.unpack_from('>f',record,o)[0] for o in offsets]
        nodes.append(dict(index=i,name=strings[0],texture=strings[1],type=words([0x54])[0],position=floats([0,4]),scale=floats([0x20,0x24]),parent=words([0x38])[0],size=words([0x48,0x4c]),material=words([0x60])[0],geometry=words([0x74,0x78,0x7c,0x80]),uv=words([0x84,0x88,0x8c,0x90])))
    return dict(node_count=count,nodes=nodes)
copies=[]; references=[]; counts={'archives':0,'resources':0,'lsp_checked':0,'excluded':0}; errors=[]
for p in ROOT.rglob('*.arc'):
    if re.fullmatch(r'msg_.*_pl.*\.arc',p.name,re.I) or p.name.lower() in ('tenka_msg000.arc','tenka_msg001.arc'):
        counts['excluded']+=1; continue
    try:
        with p.open('rb') as f:
            h=f.read(8)
            if h[:4]!=b'\0CRA': continue
            version,count=struct.unpack_from('>HH',h,4)
            table=f.read(count*80)
            counts['archives']+=1
            for i in range(count):
                rec=table[i*80:(i+1)*80]
                name=rec[:64].split(b'\0')[0].decode('ascii','replace')
                typ,comp,packed,offset=struct.unpack_from('>IIII',rec,64)
                counts['resources']+=1
                if not quest.search(name) and typ!=0x60DD1B16: continue
                f.seek(offset); blob=f.read(comp)
                try: raw=zlib.decompress(blob)
                except zlib.error:
                    if comp!=packed>>3: raise
                    raw=blob
                if quest.search(name):
                    copies.append(dict(path=str(p),index=i,name=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
                if typ==0x60DD1B16:
                    counts['lsp_checked']+=1
                    if b'quest' not in raw.lower(): continue
                    out=OUT/(p.stem+'__'+str(i)+'.lsp')
                    out.write_bytes(raw)
                    parsed=parse_lsp(raw)
                    refs=[n for n in parsed['nodes'] if 'quest' in (n['texture']+' '+n['name']).lower()]
                    references.append(dict(path=str(p),index=i,name=name,extracted=str(out),node_count=parsed['node_count'],nodes=refs))
    except Exception as e: errors.append(dict(path=str(p),error=str(e)))

d=dict(counts=counts,copies=copies,references=references,errors=errors)
(OUT/'QUEST_DEPENDENCY_AUDIT.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
print(json.dumps(dict(counts=counts,copy_count=len(copies),reference_count=len(references),errors=errors),indent=2))
