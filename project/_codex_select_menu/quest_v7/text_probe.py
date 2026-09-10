exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7')
for rel in ['eng/tenka/smith.arc','eng/tenka/tenka_id.arc']:
 a=arc.parse_arc(ROM/rel)
 for i in [0,1,2]:
  raw=arc.unpack(a.entries[i]);print(rel,i,len(raw),raw[:96].hex());(O/(Path(rel).stem+f'_{i}.bin')).write_bytes(raw)
  if i==2:
   for enc in ['utf-16-be','utf-8']:
    text=raw.decode(enc,errors='replace');print(enc,repr(text[:250]).encode('ascii','backslashreplace').decode())
for f in ['smith_55_nodes.json','tenka_id_59_nodes.json']:
 ns=json.loads((O/f).read_text())
 print(f)
 for n in ns:
  if ('text' in n['name'].lower() or '1p' in n['name'].lower() or '2p' in n['name'].lower() or 'player' in n['name'].lower()):print(n)

