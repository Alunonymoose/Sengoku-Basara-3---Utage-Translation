from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7\render_records.py')
s=p.read_text().split('for start in [500,520,540]:')[0]
s+="""
O=O.parent/'quest_v8'
ar=arc.parse_arc(O/'release/root/PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/smith.arc');raw=arc.unpack(ar.entries[25]);n=struct.unpack_from('>I',raw,12)[0];base=16+n*8
sheet=Image.new('RGBA',(1900,8*132),(32,32,32,255));d=ImageDraw.Draw(sheet)
for k,idx in enumerate([282,490,272,480,281,489,248,456]):
 off,ln=struct.unpack_from('>II',raw,16+idx*8);v=struct.unpack_from('>'+str(ln)+'H',raw,base+off*2);d.text((5,k*132+12),str(idx),fill='white');sheet.alpha_composite(render(v),(60,k*132))
sheet.convert('RGB').save(O/'ENGLISH_PROOF.png')
"""
exec(compile(s,str(p),'exec'))
