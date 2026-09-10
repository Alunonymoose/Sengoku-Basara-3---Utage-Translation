from pathlib import Path
import sys,json
from PIL import Image
W=Path(__file__).resolve().parent
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
sys.path.insert(0,str(W/'layout'))
import arc_tools as A
from repair_native_cells import patch_bc3_rect,transplant,block_ids
from inspect_layout import decode
from build_free_battle_v6 import xet_info
ROOT=Path(r'E:\Utage Patching New')
BASE=W/'baseline/PS3_GAME/USRDIR/nativePS3/rom/eng'
OUT=W/'main_assets';OUT.mkdir(exist_ok=True)
a=A.parse_arc(BASE/'quest/menu.arc');changes=[]
def save(idx,new,rect,why,extra=None):
    old=A.unpack(a.entries[idx]);assert len(old)==len(new) and old[:20]==new[:20]
    ids=set(block_ids(old,rect));start=xet_info(old)['texture_offset']
    dif=[i for i in range(xet_info(old)['payload_size']//16) if old[start+i*16:start+(i+1)*16]!=new[start+i*16:start+(i+1)*16]]
    assert set(dif)<=ids
    p=OUT/f'entry_{idx:02d}.xet';p.write_bytes(new);im=decode(new);im.save(OUT/f'entry_{idx:02d}.png')
    mask=im.getchannel('G').crop(rect);Image.merge('RGB',(mask,)*3).save(OUT/f'entry_{idx:02d}_crop.png')
    changes.append({'entry':idx,'name':a.entries[idx].name,'source_sha256':A.sha256(old),'sha256':A.sha256(new),'path':str(p),'rect':rect,'reason':why,'changed_blocks':len(dif),'non_target_blocks_preserved':True,'extra':extra})

# New English heading, confined to the native Japanese-logo UV cell.
idx=35;raw=A.unpack(a.entries[idx]);rect=(0,240,288,360);im=decode(raw)
master=Image.open(W/'heading/quests_heading_mask_master.png').convert('L')
bb=master.point(lambda p:255 if p>=48 else 0).getbbox();assert bb
mask=master.crop(bb);factor=min(280/mask.width,100/mask.height)
mask=mask.resize((int(mask.width*factor),int(mask.height*factor)),Image.Resampling.LANCZOS)
mask=mask.point(lambda p:0 if p<5 else p)
im.paste((123,0,123,0),rect);const=Image.new('L',mask.size,123)
im.paste(Image.merge('RGBA',(const,mask,const,mask)),(4,240+(120-mask.height)//2))
new=patch_bc3_rect(raw,im,rect);save(idx,new,rect,'English QUESTS heading from generated lettering mask',{'master_bbox':bb,'fitted_size':mask.size})

# Already translated in the installed Tenka texture; reuse only its bottom prompt cell.
donor=A.parse_arc(ROOT/'PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/tenka_id.arc')
hit=next(e for e in donor.entries if e.name.endswith('tenka_007_ID_HQ'))
raw=A.unpack(a.entries[36]);ref=A.unpack(hit);rect=(0,452,512,512)
assert xet_info(raw)==xet_info(ref)
new=transplant(raw,ref,rect);save(36,new,rect,'Select a battle location. from existing English Tenka asset',{'donor_sha256':A.sha256(ref)})

# Preserve all number glyphs and replace only the Japanese currency unit with SH Z.
donor=A.parse_arc(BASE/'select/c_common.arc')
hit=next(e for e in donor.entries if e.name.endswith('common_009_ID_HQ'))
raw=A.unpack(a.entries[40]);ref=A.unpack(hit);rect=(200,0,256,64)
assert xet_info(raw)==xet_info(ref)
new=transplant(raw,ref,rect);save(40,new,rect,'English currency marker from current select common_009',{'donor_sha256':A.sha256(ref)})
(OUT/'MAIN_ASSETS_REPORT.json').write_text(json.dumps(changes,indent=2))
print(json.dumps(changes,indent=2))
