from PIL import Image
import numpy as np
from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v2\source\jpn\035__charasele_00_000_ID_HQ.png')
x=np.asarray(Image.open(p).convert('RGBA')).astype(float)
y=x[:,:,3];co=x[:,:,0]-128;cg=x[:,:,2]-128
rgb=np.stack([y+co-cg,y+cg,y-co-cg,x[:,:,1]],axis=2)
a=Image.fromarray(np.uint8(np.clip(rgb,0,255)))
bg=Image.new('RGBA',a.size,(25,25,25,255));bg.alpha_composite(a);bg.convert('RGB').save(r'E:\Utage Patching New\_codex_select_menu\quest_v3\ycocg_test.png')
