exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');a=arc.parse_arc(ROM/'eng/tenka/smith.arc');t=arc.unpack(a.entries[0]);c=arc.unpack(a.entries[24]);records=[struct.unpack_from('>4H',t,32+i*8) for i in range(struct.unpack_from('>I',t,8)[0])]
for ch in [' ','P','r','o','f','i','t','a','b','l','e']:
 g=struct.unpack_from('>H',c,8+ord(ch)*2)[0];print(ch,g,records[g])
im=decode(arc.unpack(a.entries[23]));im.save(O/'font20_raw.png');preview(unpack_color(im),O/'font20_color.png')
