from pathlib import Path
import sys,io,json,struct
import numpy as np
from PIL import Image
W=Path(__file__).parent
V2=W.parent/'quest_v2'
ROOT=Path(r'E:\Utage Patching New')
ROM=ROOT/'PS3_GAME/USRDIR/nativePS3/rom'
sys.path.insert(0,str(V2/'rewards'))
from audit_rewards import decode,arc,xet_info,lsp_parse
sys.path.insert(0,str(V2/'layout'))
from repair_native_cells import patch_bc3_rect,transplant

def unpack_color(im):
    x=np.asarray(im.convert('RGBA')).astype(float);y=x[:,:,3];cr=x[:,:,0]-128;cb=x[:,:,2]-128
    return Image.fromarray(np.uint8(np.clip(np.stack([y+1.402*cr,y-.344136*cb-.714136*cr,y+1.772*cb,x[:,:,1]],axis=2),0,255)))
def pack_color(im):
    x=np.asarray(im.convert('RGBA')).astype(float);x[x[:,:,3]<1,:3]=0;r=x[:,:,0];g=x[:,:,1];b=x[:,:,2]
    y=.299*r+.587*g+.114*b;cb=(b-y)/1.772+128;cr=(r-y)/1.402+128
    return Image.fromarray(np.uint8(np.clip(np.stack([cr,x[:,:,3],cb,y],axis=2),0,255)))
def preview(im,path,bg=(25,25,25,255)):
    a=Image.new('RGBA',im.size,bg);a.alpha_composite(im);a.convert('RGB').save(path)
if __name__=='__main__':
    rows=[]
    for p in (ROM/'eng').rglob('*.arc'):
        if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc']:continue
        with p.open('rb') as f:
            h=f.read(8)
            if h[:4]!=b'\0CRA':continue
            n=struct.unpack_from('>H',h,6)[0];table=f.read(n*80)
        for i in range(n):
            name=table[i*80:i*80+64].split(b'\0')[0].decode('latin1')
            if name.endswith(('charasele_00_000_ID_HQ','yuugi_quest_002_ID_HQ')):
                rows.append(dict(path=str(p),index=i,name=name))
    (W/'ATLAS_OWNERS.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows,indent=2))
    a=arc.parse_arc(ROM/'eng/quest/menu.arc');j=arc.parse_arc(ROM/'jpn/quest/menu.arc')
    for label,obj in [('current',a),('original',j)]:
        for i in [30,35]:
            im=unpack_color(decode(arc.unpack(obj.entries[i])));preview(im,W/f'{label}_{i}.png')
