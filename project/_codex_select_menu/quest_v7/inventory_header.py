exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');found=[]
for p in (ROM/'eng').rglob('*.arc'):
 if p.name.startswith('msg_') or p.name in ['tenka_msg000.arc','tenka_msg001.arc'] or any(x in ['demo','og','backup'] for x in p.parts) or 'backup' in p.name.lower():continue
 with p.open('rb') as f:
  h=f.read(8)
  if h[:4]!=b'\0CRA':continue
  tb=f.read(struct.unpack_from('>H',h,6)[0]*80)
 for i in range(len(tb)//80):
  name=tb[i*80:i*80+64].split(b'\0')[0].decode('latin1')
  if ('\\name\\name_' in name or name.endswith(('tenka_005_ID_HQ','common_013_ID_HQ','lsp\\jpn\\tenka\\soubi_00','lsp\\jpn\\tenka\\top_00'))):found.append(dict(path=str(p),index=i,name=name))
(O/'HEADER_OWNERS.json').write_text(json.dumps(found,indent=2))
print('owners',len(found),'name archives',len(set(r['path'] for r in found if '\\name\\' in r['name'])))
print('\n'.join(str(r) for r in found if r['name'].endswith('name_022_ID_HQ')))
