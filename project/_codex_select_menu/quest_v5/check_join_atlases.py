from build_v5 import *
reference=unpack_color(decode(arc.unpack(arc.parse_arc(ROM/'eng/title.arc').entries[324]))).crop((120,384,260,448)).tobytes()
for row in json.loads((O/'OWNERS_V5.json').read_text()):
 if not row['name'].endswith('common\\common_00'):continue
 a=arc.parse_arc(Path(row['path']));found=False
 for e in a.entries:
  if e.name.endswith('common_000_ID_HQ'):
   image=unpack_color(decode(arc.unpack(e)));assert image.crop((120,384,260,448)).tobytes()==reference,row['path']
   crop=image.crop((0,384,512,448));preview(crop,O/('join_'+Path(row['path']).stem+'.png'));found=True
 print(Path(row['path']).name, 'local crop matches' if found else 'uses shared atlas')
