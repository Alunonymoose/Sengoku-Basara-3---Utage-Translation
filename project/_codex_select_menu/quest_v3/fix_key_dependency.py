from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3\build_charasele.py');s=p.read_text().replace('from scipy import ndimage as ndi','from PIL import ImageDraw')
a=s.index('seed=np.zeros');b=s.index('arr[:,:,3]=fg')
s=s[:a]+'''padded=Image.new('L',(master.width+2,master.height+2),255);padded.paste(Image.fromarray(possible.astype('uint8')*255),(1,1));ImageDraw.floodfill(padded,(0,0),127)
bg=(np.array(padded)[1:-1,1:-1]==127)|((r>220)&(b>220)&(g<55))
fg=~bg
fg=np.asarray(Image.fromarray(fg.astype('uint8')*255).filter(ImageFilter.MinFilter(3)))>0
''' +s[b:];p.write_text(s)
