"""Synchronize existing English quest-title textures into character select only."""
from pathlib import Path
import sys, json, zipfile, io, shutil
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

WORK = Path(__file__).resolve().parent
ROOT = Path(r'E:\Utage Patching New')
sys.path.insert(0, str(ROOT / '_codex_tenka_v6'))
import arc_tools as arc
from build_free_battle_v6 import xet_info, dds_header

REL = Path('PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc')
QUEST = ROOT / 'PS3_GAME/USRDIR/nativePS3/rom/eng/quest'
NAME = 'Utage_Select_Quest_Titles_V1_2026-09-08_ROOT_READY'
STAGE = WORK / NAME
PACKAGE = WORK / (NAME + '.zip')
BACKUP = WORK / 'BACKUP_select_c_common_PRE_2026-09-08.zip'
SOURCE_SHA = 'fc0a08a9b50b07662774616f457795670ecd9b7ba11e54bfcddd4082a5e71f2f'

def decode(raw):
    i = xet_info(raw)
    data = raw[i['texture_offset']:i['texture_offset']+i['payload_size']]
    return Image.open(io.BytesIO(dds_header(i['width'],i['height'],i['payload_size'],i['fourcc'])+data)).convert('RGBA')

def main():
    source = arc.parse_arc(ROOT / REL)
    assert arc.sha256(source.data) == SOURCE_SHA, 'Live c_common has changed; rebuild from a reviewed source.'
    assert source.endian == '>' and source.version == 8
    inventory = json.loads((WORK/'SELECT_INVENTORY.json').read_text())
    targets = [r for r in inventory if r['archive']=='c_common.arc' and '\\quest\\quest_' in r['name']]
    assert len(targets) == 31
    combined = arc.parse_arc(QUEST / 'quest_id.arc')
    replacements, changes, donor_guards = {}, [], {}
    previews=[]
    for n,row in enumerate(targets):
        assert row['index'] == 31+n and row['name'] == rf'id\texture\jpn\quest\quest_{n:03d}_ID_HQ'
        old = source.entries[row['index']]
        before = arc.unpack(old)
        assert arc.sha256(before) == row['sha256'] and old.name == row['name']
        donor_path = QUEST/f'q{n:03d}_id.arc'
        donor = arc.parse_arc(donor_path)
        donor_guards[donor_path] = arc.sha256(donor.data)
        hits=[e for e in donor.entries if e.name==old.name and e.type_hash==old.type_hash]
        assert len(hits)==1
        raw=arc.unpack(hits[0])
        siblings=[e for e in combined.entries if e.name==old.name and e.type_hash==old.type_hash]
        assert len(siblings)==1 and arc.unpack(siblings[0])==raw, 'English quest copies disagree'
        assert xet_info(before)==xet_info(raw)
        assert raw[:20]==before[:20] and len(raw)==len(before)==65556
        assert before!=raw
        im=decode(raw)
        # Green is the font mask for these shader-packed game textures.
        bounds=[]
        for y in (0,64):
            bbox=im.getchannel('G').crop((0,y,512,y+64)).point(lambda p:255 if p>30 else 0).getbbox()
            assert bbox and 0<=bbox[0]<bbox[2]<=512 and 0<=bbox[1]<bbox[3]<=64
            bounds.append(bbox)
        replacements[old.index]=raw
        changes.append({'entry_index':old.index,'resource':old.name,'source_sha256':arc.sha256(before),
                        'output_sha256':arc.sha256(raw),'donor':str(donor_path.relative_to(ROOT)),
                        'donor_entry':hits[0].index,'matching_quest_id_copy':True,
                        'texture':xet_info(raw),'green_mask_row_bounds':bounds})
        previews.append((n,decode(before),im))
    out=arc.rebuild(source,replacements)
    dest=STAGE/REL;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(out)
    parsed=arc.parse_arc(dest)
    assert parsed.magic==source.magic and parsed.version==source.version and len(parsed.entries)==len(source.entries)
    changed=[]; preserved=[]; inherited_sizes=[]
    for old,new in zip(source.entries,parsed.entries):
        assert (old.name,old.type_hash,old.flags,old.raw_size)==(new.name,new.type_hash,new.flags,new.raw_size)
        raw=arc.unpack(new)
        assert len(raw)==len(arc.unpack(old))
        if len(raw)!=new.raw_size:
            assert new.index not in replacements
            inherited_sizes.append({'index':new.index,'name':new.name,'declared':new.raw_size,'actual':len(raw)})
        if new.index in replacements:
            assert raw==replacements[new.index];changed.append(new.index)
        else:
            assert new.compressed==old.compressed;preserved.append(new.index)
    assert changed==list(range(31,62)) and len(preserved)==45
    for page in range(2):
        group=previews[page*16:(page+1)*16]
        canvas=Image.new('RGB',(1060,50+len(group)*72),(22,31,27));d=ImageDraw.Draw(canvas)
        font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',19)
        d.text((16,12),'Current character select',font=font,fill='white')
        d.text((545,12),'English quest title copied into character select',font=font,fill='white')
        for j,(n,before,after) in enumerate(group):
            for col,im in enumerate((before,after)):
                # Display only the first 64px state, with green-channel opacity, for legible proof.
                mask=im.getchannel('G').crop((0,0,512,64))
                ink=Image.new('RGB',(512,64),(155,255,132))
                canvas.paste(ink,(12+col*530,48+j*72),mask)
        canvas.save(WORK/f'SELECT_QUEST_BEFORE_AFTER_{page+1}.png')
    manifest={'patch':NAME,'created_utc':datetime.now(timezone.utc).isoformat(),
              'status':'offline_validation_pass_runtime_required','scope':'one archive: eng/select/c_common.arc',
              'source_sha256':SOURCE_SHA,'output_sha256':arc.sha256(out),
              'archive_entries':len(parsed.entries),'changed_texture_count':len(changed),
              'untouched_compressed_entries':len(preserved),'entry_names_types_flags_order_preserved':True,
              'all_xet_headers_and_dimensions_preserved':True,'lsp_compressed_bytes_preserved':True,
              'internal_jpn_resource_names_preserved':True,'runtime_test':'required',
              'preserved_original_size_conventions':inherited_sizes,
              'wording_policy':'Exact existing English quest-menu wording, including SWORDSMANS DUEL; no new translation or font rendering.',
              'changes':changes}
    (STAGE/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    readme='''Utage character-select quest titles - 2026-09-08

This update synchronizes all 31 quest-title textures in rom/eng/select/c_common.arc
with the existing English titles in rom/eng/quest/q000_id.arc through q030_id.arc.
Both 512x64 texture states are copied inside each original 512x128 resource.

Only PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc is included.
Merge PS3_GAME into your existing patched game root and overwrite this one file.
Use this as an add-on to your current English installation, not a full-game patch.

All 45 other entries, including the character-select layout, are preserved as
identical compressed bytes. Resource names, texture headers, dimensions, flags,
entry order, and total resource count are unchanged. No dialogue, conquest-map
messages, waza sheets, or other game files are modified by this patch.

Offline validation passed: archive resources, donor equality, layout preservation,
package CRC and SHA-256. RPCS3 cold-boot testing remains required. In Quest mode,
check character select for quests 01 through 31, both selection states, title
alignment, two-player selection, and return/confirm navigation.

Wording is inherited exactly from the existing English quest menu. In particular,
quest 02 remains SWORDSMAN'S DUEL for consistency; its Japanese title is literally
Gentlemen's Duel. This patch does not independently revise the quest translations.

Rollback: BACKUP_select_c_common_PRE_2026-09-08.zip restores the exact previous
c_common.arc. Keep the backup; avoid using it after later edits to this archive.
'''
    (STAGE/'README.txt').write_text(readme,encoding='utf-8')
    if not BACKUP.exists():
        with zipfile.ZipFile(BACKUP,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            z.writestr(REL.as_posix(),source.data)
    with zipfile.ZipFile(BACKUP) as z:
        assert z.testzip() is None and arc.sha256(z.read(REL.as_posix()))==SOURCE_SHA
    expected={p.relative_to(STAGE).as_posix():arc.sha256(p.read_bytes()) for p in STAGE.rglob('*') if p.is_file()}
    assert set(expected)=={REL.as_posix(),'MANIFEST.json','README.txt'}
    with zipfile.ZipFile(PACKAGE,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in sorted(expected):z.write(STAGE/rel,rel)
    with zipfile.ZipFile(PACKAGE) as z:
        assert z.testzip() is None
        assert {n:arc.sha256(z.read(n)) for n in z.namelist()}==expected
    sha=arc.sha256(PACKAGE.read_bytes())
    PACKAGE.with_suffix('.zip.sha256').write_text(sha+'  '+PACKAGE.name+'\n')
    report={**manifest,'package':str(PACKAGE),'package_sha256':sha,'package_size':PACKAGE.stat().st_size,
            'zip_crc_pass':True,'zip_payload_hashes_match':True,'backup':str(BACKUP),
            'backup_sha256':arc.sha256(BACKUP.read_bytes()),'installed':False}
    (WORK/'SELECT_QUEST_TITLES_V1_VALIDATION.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ['status','changed_texture_count','untouched_compressed_entries','package','package_sha256','installed']},indent=2))

if __name__=='__main__':main()
