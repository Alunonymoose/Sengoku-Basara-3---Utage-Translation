import sys
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import *
from PIL import ImageDraw
O=W.parent/'quest_v4';proof=Image.new('RGBA',(660,390),(204,234,163,255));d=ImageDraw.Draw(proof)
ref=Image.open(O/'cell_2.png').convert('RGBA');a=np.asarray(ref.getchannel('A')).astype(float);reports=[]
for i,(label,raw) in enumerate([('Before', (W/'charasele_v3.tex').read_bytes()),('Corrected encoding',(O/'charasele_v4.tex').read_bytes()),('Uncompressed source',None)]):
 im=unpack_color(decode(raw)).crop((0,240,288,360)) if raw else ref
 d.text((5,i*130+5),label,fill='black');proof.alpha_composite(im,(150,i*130+5));aa=np.asarray(im.getchannel('A')).astype(float);reports.append(dict(label=label,alpha_rmse=float(np.sqrt(((a-aa)**2).mean())),stray_pixels=int(((a==0)&(aa>20)).sum())))
proof.convert('RGB').save(O/'HEADING_ENCODING_COMPARISON.png');(O/'CODEC_CHECK.json').write_text(json.dumps(reports,indent=2));print(reports)
