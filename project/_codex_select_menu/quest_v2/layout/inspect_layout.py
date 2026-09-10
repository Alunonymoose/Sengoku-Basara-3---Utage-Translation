from pathlib import Path
import sys,struct,json,io
from PIL import Image,ImageDraw
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as A
from build_free_battle_v6 import xet_info,dds_header
from build_v18_dialogue_alignment import node_names
OUT=Path(__file__).parent
ROOT=Path(r'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom')
def parse(raw):
    count,names=node_names(raw)
    cursor=raw.find(b'\0\0\0\x08SysRoot\0',16+176*count)
    nodes=[]
    for idx in range(count):
        strings=[]
        for j in range(2):
            n=struct.unpack_from('>I',raw,cursor)[0]
            strings.append(raw[cursor+4:cursor+3+n].decode('latin1'));cursor+=4+n
        o=16+idx*176
        ints=lambda offs:[struct.unpack_from('>i',raw,o+x)[0] for x in offs]
        flts=lambda offs:[struct.unpack_from('>f',raw,o+x)[0] for x in offs]
        nodes.append(dict(index=idx,name=strings[0],texture=strings[1],position=flts([0,4]),scale=flts([0x20,0x24]),parent=ints([0x38])[0],size=ints([0x48,0x4c]),id=ints([0x50])[0],type=ints([0x54])[0],material=ints([0x60])[0],geometry=ints(range(0x74,0x84,4)),uv=ints(range(0x84,0x94,4))))
    assert [n['name'] for n in nodes]==names
    return nodes
def decode(raw):
    inf=xet_info(raw);start=inf['texture_offset']
    return Image.open(io.BytesIO(dds_header(inf['width'],inf['height'],inf['payload_size'],inf['fourcc'])+raw[start:start+inf['payload_size']])).convert('RGBA')
def main():
    for lang in ['eng','jpn']:
        a=A.parse_arc(ROOT/lang/'quest/menu.arc')
        d=OUT/lang;d.mkdir(exist_ok=True)
        entries=[];textures={}
        for e in a.entries:
            raw=A.unpack(e)
            row=dict(index=e.index,name=e.name,type=e.type_hash,size=len(raw),sha256=A.sha256(raw))
            if raw[:4]==b'\0XET':
                im=decode(raw);im.save(d/(str(e.index)+'_'+e.name.split('\\')[-1]+'.png'));textures[e.name]=im
                row['xet']=xet_info(raw)
            if raw[:4]==b'\0PSL':
                (d/'menu.lsp').write_bytes(raw)
                nodes=parse(raw)
                (d/'nodes.json').write_text(json.dumps(nodes,indent=2))
            entries.append(row)
        (d/'entries.json').write_text(json.dumps(entries,indent=2))
        print(lang,'archive',A.sha256(a.data),'entries',len(entries),'nodes',len(nodes))
        canvas=Image.new('RGB',(1100,((len(textures)+2)//3)*300),(30,40,30));draw=ImageDraw.Draw(canvas)
        for j,(name,im) in enumerate(textures.items()):
            x=(j%3)*366;y=(j//3)*300
            draw.text((x+4,y+4),name.split('\\')[-1],fill='white')
            v=Image.merge('RGB',(im.getchannel('G'),)*3);v.thumbnail((358,270));canvas.paste(v,(x+4,y+24))
        canvas.save(d/'CONTACT.png')
        for n in nodes:
            if n['type']==2 and n['texture'] in textures:
                im=textures[n['texture']];u,v,w,h=n['uv'];crop=im.crop((u,v,w,h))
                if 0<crop.width<1500 and 0<crop.height<1500: crop.save(d/(f"node_{n['index']:03d}.png"))
if __name__=='__main__':main()
