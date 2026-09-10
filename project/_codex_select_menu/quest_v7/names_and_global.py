exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');sheet=Image.new('RGBA',(1280,768),(70,70,70,255))
for i in range(30):
 a=arc.parse_arc(ROM/f'eng/tenka/tenka_pl{i:03d}.arc');im=unpack_color(decode(arc.unpack(a.entries[0])));sheet.alpha_composite(im,(i%5*256,i//5*128))
sheet.convert('RGB').save(O/'NAMES_CONTACT.png')
a=arc.parse_arc(ROM/'eng/basara.arc')
print('\n'.join(f'{e.index} {e.name} {e.raw_size}' for e in a.entries if 'msg' in e.name or any(x in e.name for x in ['item','menuki','wep','shop'])))
