exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py').read().split("if __name__")[0])
O=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v7');a=arc.parse_arc(ROM/'eng/tenka/smith.arc');csa=arc.unpack(a.entries[24]);mp={struct.unpack_from('>H',csa,8+i*2)[0]:chr(i) for i in range(128)};mp.pop(65535,None)
for idx in [1,25]:
 raw=arc.unpack(a.entries[idx]);n=struct.unpack_from('>I',raw,12)[0];base=16+n*8;rows=[]
 for i in range(n):
  off,ln=struct.unpack_from('>II',raw,16+i*8);v=list(struct.unpack_from('>'+str(ln)+'H',raw,base+off*2));s=''.join(mp.get(x,'<%d>'%x) for x in v);rows.append(dict(index=i,text=s,values=v))
 (O/f'shop_{idx}.json').write_text(json.dumps(rows,indent=2));print(idx,'count',n);print('\n'.join(str(x['index'])+' '+x['text'] for x in rows if any(s in x['text'] for s in ['Profit','Magnifi','Hakas','Bumper'])))
print('ascii chars',repr(''.join(sorted(set(mp.values())))))
