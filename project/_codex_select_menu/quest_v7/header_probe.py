exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7')
a=arc.parse_arc(ROM/'eng/tenka/tenka_pl015.arc')
for e in a.entries:
 if 'texture' in e.name:
  print(e.index,e.name);preview(unpack_color(decode(arc.unpack(e))),O/('header015_'+str(e.index)+'.png'))
raw=arc.unpack(arc.parse_arc(ROM/'eng/tenka/tenka_id.arc').entries[70]);ns=lsp_parse(raw)
for i in [68,69,70,89,90,95]:
 print(ns[i]);print([(hex(k),raw[16+i*176+k:20+i*176+k].hex()) for k in range(0,116,4)])
