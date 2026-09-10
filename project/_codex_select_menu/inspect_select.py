from pathlib import Path
import sys, json, io, struct
from PIL import Image, ImageDraw
sys.path.insert(0, r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as arc
from build_free_battle_v6 import xet_info, dds_header
BASE=Path(r'E:\Utage Patching New\_codex_select_menu')
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng\select')
OUT=BASE/'source'
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for p in sorted(ROOT.glob('*.arc')):
    a=arc.parse_arc(p)
    print(p.name, len(a.entries))
    for e in a.entries:
        raw=arc.unpack(e)
        row={'archive':p.name,'index':e.index,'name':e.name,'type':f'{e.type_hash:08X}','size':len(raw),'sha256':arc.sha256(raw)}
        stem=p.stem+'__'+str(e.index).zfill(3)+'__'+e.name.split('\\')[-1]
        if raw[:4]==b'\0XET':
            inf=xet_info(raw); row['info']=inf
            start=inf['texture_offset']
            im=Image.open(io.BytesIO(dds_header(inf['width'],inf['height'],inf['payload_size'],inf['fourcc'])+raw[start:start+inf['payload_size']])).convert('RGBA')
            png=OUT/(stem+'.png'); im.save(png); row['png']=str(png)
        elif raw[:4]==b'\0PSL':
            op=OUT/(stem+'.lsp');op.write_bytes(raw);row['lsp']=str(op)
        rows.append(row)
(BASE/'SELECT_INVENTORY.json').write_text(json.dumps(rows,indent=2))
textures=[r for r in rows if 'png' in r]
for pg in range(0,len(textures),24):
    page=textures[pg:pg+24]; canvas=Image.new('RGB',(1280,((len(page)+3)//4)*255),(40,40,40));draw=ImageDraw.Draw(canvas)
    for i,r in enumerate(page):
        x=(i%4)*320;y=(i//4)*255
        draw.text((x+4,y+4),r['archive']+' #'+str(r['index']),fill='yellow')
        draw.text((x+4,y+18),r['name'].split('\\')[-1],fill='white')
        im=Image.open(r['png']); im.thumbnail((312,210)); bg=Image.new('RGBA',im.size,(30,45,40,255));bg.alpha_composite(im)
        canvas.paste(bg.convert('RGB'),(x+(320-im.width)//2,y+40))
    canvas.save(BASE/f'SOURCE_CONTACT_{pg//24+1}.jpg',quality=92)
print('textures',len(textures),'resources',len(rows))
