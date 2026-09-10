from pathlib import Path
import csv, collections, hashlib, io, json, struct, sys, zipfile

TOOLS=Path(r'E:\Utage Patching New\_codex_tenka_v6')
sys.path.insert(0,str(TOOLS))
import arc_tools as arc
from build_free_battle_v6 import xet_info, dds_header

OUT=Path(__file__).parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom')
SHROOT=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3')
def key(n): return n.replace('/','\\').rsplit('\\',1)[-1].lower()
def sha(x): return hashlib.sha256(x).hexdigest()
def geom(raw):
    i=xet_info(raw)
    return [i[k] for k in ('width','height','format_code','payload_size')]

rows=[]
archives=[]
for p in sorted((ROOT/'eng/select').glob('*.arc')):
    a=arc.parse_arc(p)
    j=ROOT/'jpn/select'/p.name
    archives.append(dict(archive=p.name,bytes=len(a.data),sha256=sha(a.data),count=len(a.entries),jpn_identical=j.exists() and j.read_bytes()==a.data))
    for e in a.entries:
        r=arc.unpack(e)
        row=dict(archive=p.name,index=e.index,name=e.name,key=key(e.name),type=f'0x{e.type_hash:08X}',raw_size=len(r),sha256=sha(r),magic=r[:4].hex())
        if r[:4]==b'\0XET': row['geometry']=geom(r)
        rows.append(row)

keys={r['key'] for r in rows}
refs=collections.defaultdict(list)
with open(r'E:\SAMURAI HEROES\SH_ARC_MAP\sh_arc_map.csv',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        if key(r['internal_name']) in keys:
            refs[key(r['internal_name'])].append(r)
cache={}
for row in rows:
    matches=[]
    for ref in refs[row['key']]:
        if ref['type_hash'].upper()!=row['type'].upper(): continue
        p=SHROOT/ref['arc_path']
        if not p.exists(): continue
        if str(p) not in cache: cache[str(p)]=arc.parse_arc(p)
        a=cache[str(p)]; e=a.entries[int(ref['entry_index'])]; raw=arc.unpack(e)
        m=dict(path=str(p),index=e.index,name=e.name,sha256=sha(raw),same_raw=sha(raw)==row['sha256'])
        if raw[:4]==b'\0XET':
            m['geometry']=geom(raw); m['same_geometry']=m['geometry']==row.get('geometry')
        matches.append(m)
    row['donors']=matches
    row['matching_donor_hash_count']=len({m['sha256'] for m in matches if m.get('same_geometry')})

z=SHROOT/'rom/eng/SH_ROM_ENG_ARCS.zip'
with zipfile.ZipFile(z) as f: zip_select=[n for n in f.namelist() if '/select/' in n.replace('\\','/').lower()]
report=dict(archives=archives,rows=rows,sh_select_folder_exists=(SHROOT/'rom/eng/select').exists(),sh_rom_eng_zip_select=zip_select)
(OUT/'SELECT_RESOURCE_DONOR_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(archives,indent=2))
for r in rows:
    print(r['archive'],r['index'],r['type'],r['key'],r.get('geometry',''),len(r['donors']),r['matching_donor_hash_count'])
