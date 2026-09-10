exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v10\font_probe.py').read().split('a=arc.parse_arc')[0])
for rel in ['eng/tenka/tenka_id.arc','eng/title.arc','eng/select/c_common.arc']:
 a=arc.parse_arc(ROM/rel)
 for e in a.entries:
  raw=arc.unpack(e)
  if raw[:4]==b'\0CSA' and len(raw)>=264:print(rel,e.index,e.name,'K',struct.unpack_from('>H',raw,8+75*2)[0])
