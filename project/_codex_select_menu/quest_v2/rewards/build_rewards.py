"""Build semantically mapped, cell-fitted quest reward names; no live ARC writes."""
from audit_rewards import *
sys.path.insert(0,str(OUT.parent/'layout'))
from repair_native_cells import patch_bc3_rect

MAX_GLYPH=(248,32)
PL_NAMES=['Masamune Date','Yukimura Sanada','Mitsunari Ishida','Ieyasu Tokugawa','Magoichi Saica','Kanbe Kuroda','Keiji Maeda','Tsuruhime','Kotaro Fuma','Motochika Chosokabe','Yoshitsugu Otani','Yoshihiro Shimazu','Oichi','Motonari Mori','Tadakatsu Honda','Nobunaga Oda','Muneshige Tachibana','Hideaki Kobayakawa','Yoshiaki Mogami','Tenkai','Kenshin Uesugi','Kasuga','Sasuke Sarutobi','Kojuro Katakura','Matsu','Toshiie Maeda','Ujimasa Hojo','Shingen Takeda','Hisahide Matsunaga','Sorin Otomo']
PL_EXTRA={100:'Harumasa Nanbu',101:'Hirotsuna Utsunomiya',102:'Haruhisa Amago',104:'Yoritsuna Anegakoji',105:'Yoshishige Satake',106:'Kanetsugu Naoe'}
PL_ALIASES={5:'Joe C. Kuroda',11:'Chester Shimazu',13:'Sunday Mori',16:'Gallop Tachibana'}
SH_NAK={
8:['','','Tsunamoto Moniwa','Shigezane Date'],
9:['Masakage Yamagata','Kansuke Yamamoto','Yataro Onikojima','Ujinao Hojo'],
10:['Tsunashige Hojo','Tadatsugu Sakai','Naomasa Ii','Takakage Kobayakawa'],
11:['Motoharu Kikkawa','Chikasada Kira','Nobuchika Chosokabe','Toshihisa Shimazu'],
12:['Iehisa Shimazu','Yoshikage Asakura','Kazumasa Isono','Sakon Shima'],
13:['Hideie Ukita','Shigekane Suzuki','Shigetomo Suzuki','Nagamasa Kuroda'],
14:['Matabe Goto','Michinao Kono','Michiyasu Kurushima','Nagayori Murai'],
15:['Nagatomi Okumura','Yorikatsu Hiraoka','Masanari Inaba','Pitcher Hirano'],
16:['Catcher Moriguchi','Hidetsuna Sakenobe','Akiyasu Shimura','Nobuchika Kita'],
17:['Masazane Kunohe','Sukemasa Ota','Ujimoto Makabe','Takasada Haga'],
18:['Takatsugu Haga','Akisada Shioya','Ujimasa Uchigashima','Hyogonosuke Yokomichi'],
19:['Shikanosuke Yamanaka','Danzo Kato','Saizo Kirigakure','Tiger'],
20:['Takatora Todo','Hanzo Hattori','Fairlie Muto','Feather Nakatake'],
21:['Yasukatsu Owafuri','Naoshige Ono','Muneharu Shimizu','Sadatoshi Fukuhara'],
22:['Ujisato Gamo','Katsuie Shibata','Yorisato Gamo','Hyogo Mai'],
23:['Yoshimasa Satake','Magoroku Saica','Tadasumi Tani','Chikamasa Fukudome'],
24:['Ekei Ankokuji','Yoshinao Oniniwa','Genan Hojo','Tadamoto Niiro']}

def glyph_cell(im):
    bbox=im.getchannel('A').getbbox()
    if not bbox:return Image.new('RGBA',(256,48),(123,0,123,0)),None
    glyph=im.getchannel('A').crop(bbox)
    factor=min(1,MAX_GLYPH[0]/glyph.width,MAX_GLYPH[1]/glyph.height)
    if factor<1:glyph=glyph.resize((max(1,round(glyph.width*factor)),max(1,round(glyph.height*factor))),Image.Resampling.LANCZOS)
    out=Image.new('RGBA',(256,48),(123,0,123,0));c=Image.new('L',glyph.size,123);out.paste(Image.merge('RGBA',(c,glyph,c,glyph)),((256-glyph.width)//2,(48-glyph.height)//2))
    return out,dict(source_bbox=bbox,scale=factor,glyph_size=glyph.size,bbox=out.getchannel('A').getbbox())

def main():
    data=json.loads((OUT/'REWARD_DONORS.json').read_text()); d=data['donors'];sources={};generated=[]
    for p in sorted((SH/'eng/id').glob('friend_*.arc')):
        for e in arc.parse_arc(p).entries:
            key=e.name.split('\\')[-1].lower()
            if 'cp_name_nak' in key:
                sources.setdefault(key,dict(image=decode(arc.unpack(e)),arc=str(p),index=e.index,sha256=arc.sha256(arc.unpack(e))))
    rows=[];pending=[]
    for key in sorted(d):
        if key=='cp_name_nak_009_id_hq' and not all((OUT/'new_miyoshi_glyphs'/f'{v}.png').exists() for v in ['eldest','middle','youngest']):
            pending.append(key)
            continue
        original=next(q for q in data['quest'] if q['key']==key)
        raw=arc.unpack(arc.parse_arc(Path(original['arc'])).entries[original['index']]);im=Image.new('RGBA',(original['info']['width'],original['info']['height']),(123,0,123,0))
        labels=[]
        if 'cp_name_pl' in key:
            n=int(key.split('_')[3]);texts=[PL_NAMES[n] if n<30 else PL_EXTRA[n]]
            if n in PL_ALIASES:texts.append(PL_ALIASES[n])
            donor=next((v for v in d[key] if v['source']=='sh_id'),d[key][0]);src=Image.open(donor['png'])
            for r,txt in enumerate(texts):
                if n in [27,28,29]:
                    source_png=OUT.parents[1]/'source'/f'c_story__{n:03d}__cp_name_pl_{n:03d}_ID_HQ.png';story_im=Image.open(source_png).convert('RGBA');story_im.putalpha(story_im.getchannel('A').point(lambda p:0 if p<8 else min(255,p*3)));cell,fit=glyph_cell(story_im);provenance=dict(mode='reflow existing correct English alpha glyphs; normalize faint coverage',png=str(source_png),source='c_story corresponding nameplate')
                elif n==13 and r==1 or n>=100:
                    source_png=Path(r'E:\Utage Patching New\_codex_tenka_v6\id_mass_translation\generated_english_png')/f'cp_name_pl_{n:03d}.png';src_custom=Image.open(source_png);cell,fit=glyph_cell(src_custom.crop((0,48*r,256,48*r+48)));provenance=dict(mode='reflow existing correct English alpha glyphs',png=str(source_png),physical_row=r)
                else:
                    cell,fit=glyph_cell(src.crop((0,48*r,256,48*r+48)));provenance=dict(mode='mapped English donor glyphs',arc=donor['arc'],index=donor['index'],sha256=donor['sha256'],physical_row=r)
                im.paste(cell,(0,48*r));labels.append(dict(row=r,text=txt,fit=fit,provenance=provenance))
        else:
            n=int(key.split('_')[3]);count=1 if n==27 else 4
            for r in range(count):
                if n==9 and r<3:
                    txt=['Miyoshi (Eldest)','Miyoshi (Middle)','Miyoshi (Youngest)'][r];source_png=OUT/'new_miyoshi_glyphs'/(['eldest','middle','youngest'][r]+'.png');cell,fit=glyph_cell(Image.open(source_png));prov=dict(mode='generated exact English lettering',png=str(source_png))
                elif n==26 and r>0:
                    txt=['','Kazumasa Sogo','Kanenaka Shichijo','Buddha-Faced Kumahachi'][r]
                    source_png=Path(r'E:\Utage Patching New\_codex_tenka_v6\id_mass_translation\generated_english_png\cp_name_nak_026.png');src=Image.open(source_png);cell,fit=glyph_cell(src.crop((0,98+23*r,256,98+23*(r+1))));prov=dict(mode='reflow existing correct English glyphs',png=str(source_png),source_box=[0,98+23*r,256,98+23*(r+1)])
                elif n==27:
                    txt='Motosuke Kunishi';source_png=Path(r'E:\Utage Patching New\_codex_tenka_v6\id_mass_translation\generated_english_png\cp_name_nak_027.png');src=Image.open(source_png);cell,fit=glyph_cell(src);prov=dict(mode='reflow existing correct English glyphs',png=str(source_png),source_box=[0,0,256,256])
                else:
                    si,sr=divmod(n*4+r-5,4);txt=SH_NAK[si][sr];sk=f'cp_name_nak_{si:03d}_id_hq';donor=sources[sk]
                    cell,fit=glyph_cell(donor['image'].crop((0,sr*48,256,(sr+1)*48)));prov=dict(mode='semantically mapped official SH glyph row',arc=donor['arc'],index=donor['index'],sha256=donor['sha256'],source_key=sk,physical_row=sr)
                im.paste(cell,(0,48*r));labels.append(dict(row=r,text=txt,fit=fit,provenance=prov))
        # Full name resource is an atlas of text cells; its header and dimensions stay exact.
        edited=patch_bc3_rect(raw,im,(0,0,im.width,im.height));assert edited[:20]==raw[:20] and len(edited)==len(raw)
        target=OUT/'candidate'/f'{key}.tex';target.parent.mkdir(exist_ok=True);target.write_bytes(edited);preview=target.with_suffix('.png');decoded=decode(edited);decoded.save(preview)
        for label in labels:
            r=label['row'];b=decoded.getchannel('A').crop((0,r*48,256,r*48+48)).getbbox();assert b and b[0]>=3 and b[2]<=253 and b[1]>=5 and b[3]<=43,(key,label,b);label['decoded_bbox']=b
        rows.append(dict(key=key,path=str(target),png=str(preview),source_sha256=original['sha256'],sha256=arc.sha256(edited),info=original['info'],labels=labels))
        print(key,flush=True)
    result=dict(status='partial' if pending else 'pass',pending=pending,unique_resources=len(rows),candidate_resources=rows,resource_replacements=[dict(arc=q['arc'],index=q['index'],name=q['name'],key=q['key'],source_sha256=q['sha256'],candidate=str(OUT/'candidate'/f"{q['key']}.tex")) for q in data['quest'] if q['key'] not in pending],notes=['Original Utage atlas semantics preserved; same-index SH resources are not considered authoritative for identity.','Official donor spellings Saica, Kanbe and Mori retained.','Every text row fits inside native256x48 physical cell with glyph<=248x32.','No live game archives modified.'])
    (OUT/'REWARD_CANDIDATES.json').write_text(json.dumps(result,indent=2))
    all_labels=[(a,lab) for a in rows for lab in a['labels']]
    for start in range(0,len(all_labels),40):
        page=Image.new('RGB',(1150,((min(40,len(all_labels)-start)+1)//2)*76),(52,53,35));draw=ImageDraw.Draw(page)
        for j,(a,lab) in enumerate(all_labels[start:start+40]):
            x=(j%2)*575;y=(j//2)*76;draw.text((x,y),a['key']+' row '+str(lab['row']),fill='yellow');cell=Image.open(a['png']).crop((0,lab['row']*48,256,(lab['row']+1)*48));page.paste(cell,(x+260,y+15),cell)
        page.save(OUT/f'REWARD_CANDIDATES_{start//40:02d}.png')
    print(json.dumps(dict(status='pass',unique_resources=len(rows),archive_local_replacements=len(data['quest'])),indent=2))
if __name__=='__main__':main()
