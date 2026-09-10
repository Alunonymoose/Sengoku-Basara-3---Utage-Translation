from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7\render_records.py')
s=p.read_text().split('for start in [500,520,540]:')[0]
s+="\nO=O.parent/'quest_v10'\nfor start in [168,336,376]:\n sheet=Image.new('RGBA',(1600,20*64),(32,32,32,255));d=ImageDraw.Draw(sheet)\n for k in range(40):\n  x=(k//20)*800;y=(k%20)*64;d.text((x,y),str(start+k),fill='white');sheet.alpha_composite(render(rs[start+k]['values']).crop((0,0,740,60)),(x+50,y))\n sheet.convert('RGB').save(O/f'NAMES_{start}.png')\n"
exec(compile(s,str(p),'exec'))

