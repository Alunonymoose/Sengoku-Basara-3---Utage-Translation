"""Repair quest atlas cells against the unchanged native LSP UV rectangles.

No archives or game installation files are written. Existing English glyph masks
are fit to their native cells; gameplay symbols are byte-exact Japanese BC3 art.
"""
from pathlib import Path
import sys,json,hashlib
from PIL import Image,ImageDraw
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as A
from build_free_battle_v6 import encode_bc3_block,xet_info
from inspect_layout import decode,parse

OUT=Path(__file__).parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom')
SHA_ENG='e4eaf22d23ea2e1d579b8101280f16700bb2c37c070ef258a5a8483f60487c7f'
SHA_JPN='aa2dc3a3496376ab7b9afa1ce8fe825c9d177c46f49b3e34a7c5b2d3e4932927'

def patch_bc3_rect(raw,image,rect):
    """Retain RGB masks even at A=0, unlike ordinary color+opacity encoding."""
    inf=xet_info(raw);b=bytearray(raw);px=image.load();offset=inf['texture_offset']
    x0,y0,x1,y1=rect
    assert all(v%4==0 for v in rect)
    for by in range(y0//4,y1//4):
        for bx in range(x0//4,x1//4):
            ps=[px[bx*4+x,by*4+y] for y in range(4) for x in range(4)]
            a=encode_bc3_block(ps)[:8]
            c=encode_bc3_block([(r,g,bb,255) for r,g,bb,aa in ps])[8:]
            i=offset+(by*(inf['width']//4)+bx)*16
            b[i:i+16]=a+c
    return bytes(b)

def block_ids(raw,rect):
    inf=xet_info(raw);x0,y0,x1,y1=rect
    assert all(x%4==0 for x in rect)
    return [y*(inf['width']//4)+x for y in range(y0//4,y1//4) for x in range(x0//4,x1//4)]

def transplant(out,source,rect):
    assert xet_info(out)==xet_info(source)
    b=bytearray(out);base=xet_info(out)['texture_offset']
    for n in block_ids(out,rect):b[base+n*16:base+n*16+16]=source[base+n*16:base+n*16+16]
    return bytes(b)

def fit_mask(out,source_im,source_box,target_box,max_size,label):
    # Shader-packed native text uses G as its coverage channel; A duplicates it.
    m=source_im.crop(source_box).getchannel('G');bb=m.point(lambda v:255 if v>25 else 0).getbbox()
    assert bb,label
    m=m.crop(bb)
    w,h=m.size;mw,mh=max_size;scale=min(mw/w,mh/h)
    target_size=(round(w*scale),round(h*scale))
    m=m.resize(target_size,Image.Resampling.LANCZOS)
    im=decode(out);x0,y0,x1,y1=target_box
    im.paste((123,0,123,0),target_box)
    x=x0+(x1-x0-m.width)//2;y=y0+(y1-y0-m.height)//2
    c=Image.new('L',m.size,123)
    im.paste(Image.merge('RGBA',(c,m,c,m)),(x,y))
    result=patch_bc3_rect(out,im,target_box)
    return result,dict(label=label,source_crop=source_box,source_ink_bbox=bb,target_cell=target_box,target_ink_box=[x,y,x+m.width,y+m.height],scale=scale)

def main():
    eng=A.parse_arc(ROOT/'eng/quest/menu.arc');jpn=A.parse_arc(ROOT/'jpn/quest/menu.arc')
    assert A.sha256(eng.data)==SHA_ENG and A.sha256(jpn.data)==SHA_JPN
    assert A.unpack(eng.entries[44])==A.unpack(jpn.entries[44])
    candidates={};reports=[]
    idx=30;e=eng.entries[idx];base=A.unpack(e);orig=A.unpack(jpn.entries[idx]);out=base
    assert e.name==jpn.entries[idx].name
    restored=[('filled_star',[216,256,264,304]),('reward_row_point',[264,256,296,304]),('five_star_underlay',[0,352,216,400])]
    allowed=set()
    for name,rect in restored:
        out=transplant(out,orig,rect);allowed.update(block_ids(out,rect))
    donor=decode(base)
    # Every target cell below is UV*2 from yuugi_quest; labels never share cells.
    jobs=[
      ('clear_time',(4,258,210,298),(0,256,216,304),(204,28)),
      ('fastest_clear_time',(0,310,264,348),(0,304,216,352),(204,26)),
      ('difficulty',(278,466,386,500),(216,456,384,504),(150,30)),
      ('reward',(392,464,510,502),(384,440,512,504),(116,28)),
      ('cleared_warriors',(0,404,308,442),(0,400,328,456),(304,30)),
      ('challenges_cleared',(0,466,274,500),(0,456,216,504),(208,24)),
    ]
    labels=[]
    for label,source_box,target_box,max_size in jobs:
        out,record=fit_mask(out,donor,source_box,target_box,max_size,label)
        labels.append(record);allowed.update(block_ids(out,target_box))
    candidates[idx]=out
    restored_proof=[]
    for name,rect in restored:
        ids=block_ids(out,rect);offset=xet_info(out)['texture_offset']
        assert all(out[offset+n*16:offset+(n+1)*16]==orig[offset+n*16:offset+(n+1)*16] for n in ids)
        restored_proof.append(dict(symbol=name,physical_cell=rect,exact_original_bc3_blocks=len(ids)))
    reports.append(dict(entry=idx,resource=e.name,source_sha256=A.sha256(base),output_sha256=A.sha256(out),labels=labels,restored=restored_proof,allowed_block_ids=sorted(allowed)))

    idx=38;e=eng.entries[idx];base=A.unpack(e);orig=A.unpack(jpn.entries[idx]);out=base
    assert e.name==jpn.entries[idx].name
    slash=[84,432,132,496];unit=[0,432,84,496]
    out=transplant(out,orig,slash)
    im=decode(out);im.paste((123,0,123,0),unit);out=patch_bc3_rect(out,im,tuple(unit))
    candidates[idx]=out
    allowed=set(block_ids(out,slash)+block_ids(out,unit));offset=xet_info(out)['texture_offset']
    assert all(out[offset+n*16:offset+(n+1)*16]==orig[offset+n*16:offset+(n+1)*16] for n in block_ids(out,slash))
    reports.append(dict(entry=idx,resource=e.name,source_sha256=A.sha256(base),output_sha256=A.sha256(out),counter_unit='blank; count remains selected/total without redundant noun',slash_original_bc3_blocks=len(block_ids(out,slash)),allowed_block_ids=sorted(allowed)))

    for r in reports:
        idx=r['entry'];base=A.unpack(eng.entries[idx]);out=candidates[idx]
        info=xet_info(base);offset=info['texture_offset'];blocks=info['payload_size']//16
        assert out[:offset]==base[:offset] and len(out)==len(base)
        changed=[n for n in range(blocks) if base[offset+n*16:offset+(n+1)*16]!=out[offset+n*16:offset+(n+1)*16]]
        assert set(changed)<=set(r.pop('allowed_block_ids'))
        r['changed_blocks']=len(changed);r['unchanged_blocks']=blocks-len(changed)
        r['non_target_blocks_byte_preserved']=True
        (OUT/f'entry_{idx:02d}_native_cells.xet').write_bytes(out)
        decode(out).save(OUT/f'entry_{idx:02d}_native_cells.png')

    nodes=parse(A.unpack(eng.entries[44]));inds=[84,85,86,91,106,109,153,285,297]
    panel=Image.new('RGB',(1000,len(inds)*100+45),(25,35,30));draw=ImageDraw.Draw(panel)
    draw.text((180,10),'Before: sampled native cell',fill='white');draw.text((570,10),'After: same native cell',fill='white')
    for row,ni in enumerate(inds):
        n=nodes[ni];ei=next(e.index for e in eng.entries if e.name==n['texture'])
        draw.text((5,45+row*100),f"{ni} {n['name']}",fill='white')
        for col,raw in enumerate((A.unpack(eng.entries[ei]),candidates[ei])):
            im=decode(raw).crop(tuple(v*2 for v in n['uv']));im=Image.merge('RGB',(im.getchannel('G'),)*3)
            im.thumbnail((380,92));panel.paste(im,(180+390*col,45+row*100))
    panel.save(OUT/'NATIVE_CELL_BEFORE_AFTER.png')
    report=dict(status='offline_resource_validation_pass',source_eng_arc_sha256=SHA_ENG,source_jpn_arc_sha256=SHA_JPN,lsp_byte_preserved=True,lsp_sha256=A.sha256(A.unpack(eng.entries[44])),physical_coordinates_are_native_uv_times_two=True,entries=reports,runtime='requires cold boot; no game files installed')
    (OUT/'NATIVE_CELL_VALIDATION.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
