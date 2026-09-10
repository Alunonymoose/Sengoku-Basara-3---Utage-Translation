from common import *
rows=json.loads((W/'ATLAS_OWNERS.json').read_text());out=[]
for rec in rows:
 p=Path(rec['path'])
 if 'og' in p.parts or 'backup' in p.name:continue
 a=arc.parse_arc(p)
 for e in a.entries:
  if e.type_hash==0x60DD1B16:
   try:nodes=lsp_parse(arc.unpack(e))
   except Exception as ex:print('ERR',p,e.name,str(ex));continue
   for n in nodes:
    if n['texture'].endswith('charasele_00_000_ID_HQ'):out.append(dict(arc=str(p),lsp=e.name,**n))
(W/'CHARASELE_NODES.json').write_text(json.dumps(out,indent=2))
seen=set()
for n in out:
 k=(n['name'],tuple(n['uv']))
 if k not in seen:print(k);seen.add(k)
