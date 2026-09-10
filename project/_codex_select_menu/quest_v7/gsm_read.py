exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7')
a=arc.parse_arc(ROM/'eng/tenka/smith.arc');raw=arc.unpack(a.entries[1]);n=struct.unpack_from('>I',raw,12)[0];base=16+n*8;rows=[]
for i in range(n):
 off,ln=struct.unpack_from('>II',raw,16+i*8);v=struct.unpack_from('>'+str(ln)+'H',raw,base+off*2)
 s=''.join(chr(x+32) if x<95 else '<%d>'%x for x in v);rows.append(dict(index=i,text=s,values=v))
(O/'SMITH_GSM.json').write_text(json.dumps(rows,indent=2));print('\n'.join(str(r['index'])+' '+r['text'] for r in rows if len(r['text'])>15)[:4000])
c=arc.unpack(a.entries[24]);print('CSA',len(c),c[:100].hex());(O/'smith_csa.bin').write_bytes(c)
