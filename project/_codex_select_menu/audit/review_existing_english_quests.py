from pathlib import Path
import collections,hashlib,io,json,sys
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as a
from build_free_battle_v6 import xet_info,dds_header

OUT=Path(__file__).parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng')
REPORT=json.loads((OUT/'QUEST_DEPENDENCY_AUDIT.json').read_text())
byname=collections.defaultdict(list)
for r in REPORT['copies']: byname[r['name']].append(r)
rows=[];tiles=[]
cache={}
for name,refs in sorted(byname.items()):
    n=name.rsplit('\\',1)[-1]
    donor_ref=next(r for r in refs if '\\quest\\q' in r['path'] and r['path'].endswith('_id.arc') and not r['path'].endswith('quest_id.arc'))
    p=Path(donor_ref['path']);arc=a.parse_arc(p);raw=a.unpack(arc.entries[donor_ref['index']]); info=xet_info(raw)
    dds=dds_header(info['width'],info['height'],info['payload_size'],info['fourcc'])+raw[info['texture_offset']:info['texture_offset']+info['payload_size']]
    im=Image.open(io.BytesIO(dds)).convert('RGBA'); green=im.getchannel('G')
    source_ref=next(r for r in refs if '\\select\\' in r['path']);source_arc=cache.setdefault(source_ref['path'],a.parse_arc(Path(source_ref['path'])));old=a.unpack(source_arc.entries[source_ref['index']])
    row=dict(name=name,donor_path=str(p),donor_entry=donor_ref['index'],donor_sha256=hashlib.sha256(raw).hexdigest(),source_entry=source_ref['index'],source_sha256=hashlib.sha256(old).hexdigest(),same_geometry=xet_info(old)==info,same_xet_header=old[:20]==raw[:20],copies=refs)
    rows.append(row)
    tile=Image.new('RGB',(528,155),(30,30,30));draw=ImageDraw.Draw(tile);draw.text((8,3),n,fill=(255,255,130));tile.paste(green.convert('RGB'),(8,20));tiles.append(tile)
for page in range((len(tiles)+11)//12):
    these=tiles[page*12:page*12+12];canvas=Image.new('RGB',(1056,155*((len(these)+1)//2)),(30,30,30))
    for i,tile in enumerate(these):canvas.paste(tile,((i%2)*528,(i//2)*155))
    canvas.save(OUT/f'EXISTING_QUEST_ENGLISH_{page+1}.png')
(OUT/'EXISTING_QUEST_ENGLISH_DONORS.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(dict(count=len(rows),all_same_geometry=all(r['same_geometry'] for r in rows),all_same_header=all(r['same_xet_header'] for r in rows),unique_copy_groups=collections.Counter(len(set(x['sha256'] for x in r['copies'])) for r in rows)),indent=2))
