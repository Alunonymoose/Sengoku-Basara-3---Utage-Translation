from pathlib import Path
import sys,json,io
from PIL import Image,ImageDraw
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as A
from build_free_battle_v6 import xet_info,dds_header
WORK=Path(__file__).resolve().parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom')
rows=[]
for lang in ('eng','jpn'):
    out=WORK/'source'/lang;out.mkdir(parents=True,exist_ok=True)
    a=A.parse_arc(ROOT/lang/'quest/menu.arc')
    for e in a.entries:
        r=A.unpack(e);row={'lang':lang,'index':e.index,'name':e.name,'type':hex(e.type_hash),'sha256':A.sha256(r)}
        if r[:4]==b'\0XET':
            inf=xet_info(r);row['info']=inf
            im=Image.open(io.BytesIO(dds_header(inf['width'],inf['height'],inf['payload_size'],inf['fourcc'])+r[inf['texture_offset']:inf['texture_offset']+inf['payload_size']])).convert('RGBA')
            path=out/(f'{e.index:03d}__'+e.name.split('\\')[-1]+'.png');im.save(path);row['png']=str(path)
            # Shader-packed previews: show RGB; alpha masks have their own artifact if needed.
            im.convert('RGB').save(path.with_name(path.stem+'_rgb.png'))
        elif r[:4]==b'\0PSL':
            path=out/'menu.lsp';path.write_bytes(r);row['lsp']=str(path)
        rows.append(row)
    textures=[r for r in rows if r['lang']==lang and 'png' in r]
    for pg in range(0,len(textures),16):
        chunk=textures[pg:pg+16];can=Image.new('RGB',(1200,((len(chunk)+3)//4)*280),(32,38,35));draw=ImageDraw.Draw(can)
        for i,r in enumerate(chunk):
            x=i%4*300;y=i//4*280;im=Image.open(r['png']);im.thumbnail((290,240));bg=Image.new('RGBA',im.size,(32,38,35,255));bg.alpha_composite(im)
            can.paste(bg.convert('RGB'),(x+(300-im.width)//2,y+35));draw.text((x+5,y+5),str(r['index'])+' '+r['name'].split('\\')[-1],fill='white')
        can.save(WORK/f'{lang}_menu_contact_{pg//16+1}.jpg',quality=94)
(WORK/'MENU_INVENTORY.json').write_text(json.dumps(rows,indent=2))
print(json.dumps([r for r in rows if r['lang']=='eng'],indent=2))
