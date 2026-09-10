exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');a=arc.parse_arc(ROM/'eng/basara.arc')
for e in a.entries:
 if 'caption' not in e.name or e.type_hash!=0x10c460e6:continue
 raw=arc.unpack(e);n=struct.unpack_from('>I',raw,12)[0];base=16+n*8;rows=[]
 for i in range(n):
  off,ln=struct.unpack_from('>II',raw,16+i*8);v=struct.unpack_from('>'+str(ln)+'H',raw,base+off*2);s=''.join(chr(x+32 if x<6 else x+33) if x<94 else '<%d>'%x for x in v);rows.append(dict(index=i,text=s,values=v))
 (O/f'caption_{e.index}.json').write_text(json.dumps(rows,indent=2));print(e.index,n,[r for r in rows if 'Profit' in r['text']][:3],rows[:2])
