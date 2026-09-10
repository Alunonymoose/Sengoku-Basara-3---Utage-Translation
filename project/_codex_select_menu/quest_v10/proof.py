from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7\render_records.py')
s=p.read_text().split('for start in [500,520,540]:')[0].replace('elif v in [65426,65425]:i+=1','elif v==65426:i+=1')
s+="""
O=O.parent/'quest_v10'
ar=arc.parse_arc(O/'release/root/PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/smith.arc');raw=arc.unpack(ar.entries[25]);n=struct.unpack_from('>I',raw,12)[0];base=16+n*8;tnf=arc.unpack(ar.entries[0]);pages={int(e.name.split('_')[-3]):unpack_color(decode(arc.unpack(e))) for e in ar.entries if e.name.startswith('msg') and e.name.endswith('_ID_HQ')}
sheet=Image.new('RGBA',(1900,8*132),(32,32,32,255));d=ImageDraw.Draw(sheet)
for k,idx in enumerate([349,557,350,558,344,552,336,544]):
 off,ln=struct.unpack_from('>II',raw,16+idx*8);v=struct.unpack_from('>'+str(ln)+'H',raw,base+off*2);d.text((5,k*132+12),str(idx),fill='white');sheet.alpha_composite(render(v),(60,k*132))
sheet.convert('RGB').save(O/'ENGLISH_PROOF.png')
"""
exec(compile(s,str(p),'exec'))



