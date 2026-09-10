from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7\render_records.py')
s=p.read_text().replace('for start in [500,520,540]:',"O=O.parent/'quest_v10'\nfor start in [408,428,448,544,564,584]:")
exec(compile(s,str(p),'exec'))


