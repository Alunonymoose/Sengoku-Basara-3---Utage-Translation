"""Resample existing quest lettering into the actual native UV cells; no new type."""
from pathlib import Path
import sys,io,json
from PIL import Image,ImageDraw
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as A
from build_free_battle_v6 import xet_info,dds_header
W=Path(__file__).resolve().parent
sys.path.insert(0,str(W/'layout'))
from repair_native_cells import patch_bc3_rect
BASE=W/'baseline/PS3_GAME/USRDIR/nativePS3/rom/eng/quest'
OUT=W/'titles';OUT.mkdir(exist_ok=True)
def decode(r):
    i=xet_info(r)
    return Image.open(io.BytesIO(dds_header(i['width'],i['height'],i['payload_size'],i['fourcc'])+r[i['texture_offset']:i['texture_offset']+i['payload_size']])).convert('RGBA')
def resize_packed(im,size):
    return Image.merge('RGBA',[c.resize(size,Image.Resampling.LANCZOS) for c in im.split()])
rows=[]; thumbs=[]
for n in range(31):
    a=A.parse_arc(BASE/f'q{n:03d}_id.arc');e=a.entries[0];raw=A.unpack(e);im=decode(raw)
    assert im.size==(512,128)
    dst=Image.new('RGBA',im.size,(123,0,123,0));fits=[]
    for y in (0,64):
        row=im.crop((0,y,512,y+64));bb=row.getchannel('G').point(lambda p:255 if p>=24 else 0).getbbox();assert bb
        # These pre-existing English title sheets use matching alpha and green text masks.
        # Alpha is the clean glyph coverage; their old encoder polluted zero-alpha RGB edges.
        bb=row.getchannel('A').point(lambda p:255 if p>=24 else 0).getbbox();assert bb
        mask=row.getchannel('A').crop(bb);crop=Image.merge('RGBA',(Image.new('L',mask.size,123),mask,Image.new('L',mask.size,123),mask))
        factor=min(350/crop.width,28/crop.height)
        size=(max(1,int(crop.width*factor)),max(1,int(crop.height*factor)))
        piece=resize_packed(crop,size);dst.paste(piece,(4,y+(64-size[1])//2))
        fits.append({'source_bbox':bb,'output_size':size,'scale':factor})
    new=patch_bc3_rect(raw,dst,(0,0,512,128));assert new[:20]==raw[:20] and len(new)==len(raw)
    actual=decode(new)
    for y in (0,64):
        bb=actual.getchannel('G').crop((0,y,512,y+64)).point(lambda p:255 if p>=24 else 0).getbbox()
        assert bb and bb[0]>=2 and bb[2]<=356 and bb[3]-bb[1]<=32,bb
    path=OUT/f'quest_{n:03d}.xet';path.write_bytes(new);actual.save(OUT/f'quest_{n:03d}.png')
    rows.append({'quest':n,'name':e.name,'source_sha256':A.sha256(raw),'sha256':A.sha256(new),'path':str(path),'fits':fits})
    thumbs.append(actual)
for page in range(2):
    chunk=thumbs[page*16:(page+1)*16];canvas=Image.new('RGB',(760,50+len(chunk)*64),(24,35,30));d=ImageDraw.Draw(canvas)
    d.text((12,12),'Decoded title textures inside the 360 x 64 menu crop (2x display)',fill='white')
    for j,im in enumerate(chunk):
        mask=im.getchannel('G').crop((0,0,360,64));ink=Image.new('RGB',mask.size,(222,240,227));canvas.paste(ink,(12,j*64+42),mask)
    canvas.save(OUT/f'TITLE_FIT_PREVIEW_{page+1}.png')
(OUT/'TITLE_FIT_REPORT.json').write_text(json.dumps(rows,indent=2))
print('Fitted and BC3-validated',len(rows),'quest titles')
