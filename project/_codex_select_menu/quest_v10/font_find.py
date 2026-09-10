exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v10\font_probe.py').read().split('a=arc.parse_arc')[0])
root=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom')
for rel in ['game.arc','eng/startup.arc','eng/init_ps3.arc']:
 p=root/rel
 if not p.exists():continue
 a=arc.parse_arc(p)
 print(rel,[(e.index,e.name,e.raw_size) for e in a.entries if 'font' in e.name or arc.unpack(e)[:4]==b'\0TNF'])
