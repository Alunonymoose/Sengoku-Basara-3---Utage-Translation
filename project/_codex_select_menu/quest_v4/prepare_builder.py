from pathlib import Path
v3=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3');v4=v3.parent/'quest_v4'
s=(v3/'build_charasele.py').read_text();s=s.replace('from common import *','import sys\nsys.path.insert(0,r"E:\\Utage Patching New\\_codex_select_menu\\quest_v3")\nfrom common import *\nW=Path(__file__).parent\nfrom codec_v4 import patch_bc3_rect');s=s.replace('charasele_v3.tex','charasele_v4.tex').replace('CHARASELE_V3_PREVIEW','CHARASELE_V4_PREVIEW');s=s.replace("im=decode(out);im.paste", "cell.save(W/f'cell_{k}.png')\n im=decode(out);im.paste")
(v4/'build_charasele_v4.py').write_text(s);(v4/'menu_lettering_key.png').write_bytes((v3/'menu_lettering_key.png').read_bytes())
