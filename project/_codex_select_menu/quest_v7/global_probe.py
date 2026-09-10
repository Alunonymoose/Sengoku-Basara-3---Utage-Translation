exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
for rel in ['game.arc','eng/startup.arc','eng/init_ps3.arc']:
 a=arc.parse_arc(ROM/rel)
 print(rel,[(e.index,e.name,e.raw_size) for e in a.entries if e.type_hash==0x10c460e6])
