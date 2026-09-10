exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v6');found=[]
for p in [*(ROM/'eng').rglob('*.arc'),*ROM.glob('*.arc')]:
 if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc'] or any(x in ['demo','og','backup'] for x in p.parts) or 'backup' in p.name.lower():continue
 with p.open('rb') as f:
  h=f.read(8)
  if h[:4]!=b'\0CRA':continue
  n=struct.unpack_from('>H',h,6)[0];tb=f.read(n*80)
 for i in range(n):
  name=tb[i*80:i*80+64].split(b'\0')[0].decode('latin1')
  if name.endswith(('mode_select_003_ID_HQ','common_000_ID_HQ')):found.append(dict(path=str(p),index=i,name=name))
(O/'OWNERS.json').write_text(json.dumps(found,indent=2))
for k,r in enumerate(found):
 raw=arc.unpack(arc.parse_arc(Path(r['path'])).entries[r['index']]);im=unpack_color(decode(raw))
 if 'common_000' in r['name']:
  preview(im.crop((0,384,512,448)),O/f'commonrow_{k}.png')
 else:preview(im,O/f'mode003_{k}.png')
 print(k,Path(r['path']).relative_to(ROM),r['index'],r['name'].split('\\')[-1],arc.sha256(raw)[:12])
