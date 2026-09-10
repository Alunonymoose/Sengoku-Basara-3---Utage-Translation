exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v10\font_probe.py').read().split('a=arc.parse_arc')[0])
a=arc.parse_arc(ROM/'eng/tenka/tenka_id.arc');src=arc.unpack(a.entries[0]);print('TNF',src[:32].hex());print([(e.index,e.name) for e in a.entries[:20]])
for c in 'Kj':
 idx=struct.unpack_from('>H',arc.unpack(a.entries[18]),8+ord(c)*2)[0];print(c,idx,struct.unpack_from('>4H',src,32+idx*8))
b=arc.parse_arc(ROM/'eng/tenka/smith.arc');raw=arc.unpack(b.entries[0]);print('DST',raw[:32].hex());print([struct.unpack_from('>4H',raw,i) for i in range(len(raw)-24,len(raw),8)])
