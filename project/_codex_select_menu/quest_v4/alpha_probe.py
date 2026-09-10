import sys,json
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
O=Path(__file__).parent;out=[]
for k,c in enumerate(json.loads((O/'CHARASELE_BUILD.json').read_text())['cells']):
 got=np.array(unpack_color(decode((O/'charasele_v4.tex').read_bytes())).crop(c['rect']))[:,:,3];want=np.array(Image.open(O/f'cell_{k}.png'))[:,:,3];false=got[want==0];out.append([k,int(false.max()),int((false>0).sum())])
print(out)
