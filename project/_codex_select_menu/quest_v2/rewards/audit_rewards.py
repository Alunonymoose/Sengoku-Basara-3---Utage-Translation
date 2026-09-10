from pathlib import Path
import sys,json,io,re,struct
from PIL import Image,ImageDraw
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as arc
from build_free_battle_v6 import xet_info,dds_header

OUT=Path(__file__).parent
UT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom')
SH=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom')
def decode(raw):
    inf=xet_info(raw); pos=inf['texture_offset']
    return Image.open(io.BytesIO(dds_header(inf['width'],inf['height'],inf['payload_size'],inf['fourcc'])+raw[pos:pos+inf['payload_size']])).convert('RGBA')
def lsp_parse(raw):
    count=struct.unpack_from('>H',raw,12)[0]; cursor=raw.find(b'\0\0\0\x08SysRoot\0',16+176*count); result=[]
    for i in range(count):
        strings=[]
        for _ in range(2):
            ln=struct.unpack_from('>I',raw,cursor)[0]; strings.append(raw[cursor+4:cursor+3+ln].decode('latin1'));cursor+=4+ln
        rec=raw[16+i*176:16+(i+1)*176]
        wi=lambda offs:[struct.unpack_from('>i',rec,j)[0] for j in offs]
        wf=lambda offs:[struct.unpack_from('>f',rec,j)[0] for j in offs]
        result.append(dict(index=i,name=strings[0],texture=strings[1],type=wi([0x54])[0],position=wf([0,4]),scale=wf([0x20,0x24]),parent=wi([0x38])[0],size=wi([0x48,0x4c]),geometry=wi([0x74,0x78,0x7c,0x80]),uv=wi([0x84,0x88,0x8c,0x90])))
    return result
def main():
    quest=[]; keyset=set(); donors={}
    for p in sorted((UT/'eng/quest').glob('*.arc')):
        a=arc.parse_arc(p)
        for e in a.entries:
            key=e.name.split('\\')[-1].lower()
            if key.startswith(('cp_name_nak','cp_name_pl')):
                raw=arc.unpack(e);keyset.add(key)
                quest.append(dict(arc=str(p),index=e.index,name=e.name,key=key,sha256=arc.sha256(raw),info=xet_info(raw)))
            if e.type_hash==0x60DD1B16:
                rows=lsp_parse(arc.unpack(e));(OUT/'quest_lsp.json').write_text(json.dumps(rows,indent=2))
    for source,root in [('ut_id',UT/'eng/id'),('sh_id',SH/'eng/id'),('sh_pause',SH/'eng/pause')]:
        for p in sorted(root.glob('*.arc')):
            if p.name.startswith('msg_'):continue
            for e in arc.parse_arc(p).entries:
                key=e.name.split('\\')[-1].lower()
                if key not in keyset:continue
                raw=arc.unpack(e);sha=arc.sha256(raw)
                rows=donors.setdefault(key,[])
                if any(d['sha256']==sha and d['source']==source for d in rows):continue
                rawpath=OUT/f'{source}__{key}__{sha[:10]}.tex'; rawpath.write_bytes(raw)
                im=decode(raw);png=rawpath.with_suffix('.png');im.save(png)
                rows.append(dict(source=source,arc=str(p),index=e.index,name=e.name,key=key,sha256=sha,raw=str(rawpath),png=str(png),info=xet_info(raw),bbox=im.getchannel('A').getbbox()))
    sheetrows=[]
    for key in sorted(keyset):
        q=next(r for r in quest if r['key']==key); a=arc.parse_arc(Path(q['arc'])); im=decode(arc.unpack(a.entries[q['index']]));im.save(OUT/f'quest__{key}.png')
        sheetrows.append((key+' QUEST',im))
        for d in donors.get(key,[]):sheetrows.append((key+' '+d['source'],Image.open(d['png'])))
    for pg in range(0,len(sheetrows),24):
        rows=sheetrows[pg:pg+24];page=Image.new('RGB',(1200,len(rows)*75),(35,52,40));draw=ImageDraw.Draw(page)
        for i,(label,im) in enumerate(rows):
            draw.text((4,i*75+4),label,fill='yellow');im.thumbnail((980,65));page.paste(im,(220,i*75),im)
        page.save(OUT/f'REWARD_AUDIT_{pg//24:02d}.png')
    (OUT/'REWARD_DONORS.json').write_text(json.dumps(dict(quest=quest,donors=donors),indent=2))
    print(json.dumps(dict(unique_names=len(keyset),resource_copies=len(quest),donors=len(donors),missing=sorted(keyset-set(donors))),indent=2))
if __name__=='__main__':main()
