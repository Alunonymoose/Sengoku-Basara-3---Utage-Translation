from pathlib import Path
from datetime import datetime,timezone
import sys,json,zipfile,hashlib
W=Path(__file__).resolve().parent
ROOT=Path(r'E:\Utage Patching New')
sys.path.insert(0,str(ROOT/'_codex_tenka_v6'))
import arc_tools as A
from build_free_battle_v6 import xet_info
NAME='Utage_Quest_Menu_V2_FIT_AND_REWARDS_ROOT_READY'
STAGE=W/NAME;ZIP=W/(NAME+'.zip')
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    baseline=json.loads((W/'BASELINE_MANIFEST.json').read_text())
    titles=json.loads((W/'titles/TITLE_FIT_REPORT.json').read_text())
    rewards=json.loads((W/'rewards/REWARD_CANDIDATES.json').read_text());assert rewards['status']=='pass' and not rewards['pending']
    title_map={r['name']:Path(r['path']).read_bytes() for r in titles}
    reward_map={r['key']:Path(r['path']).read_bytes() for r in rewards['candidate_resources']}
    for r in titles:assert sha(title_map[r['name']])==r['sha256']
    for r in rewards['candidate_resources']:assert sha(reward_map[r['key']])==r['sha256']
    assets=json.loads((W/'main_assets/MAIN_ASSETS_REPORT.json').read_text())
    menu={r['entry']:Path(r['path']).read_bytes() for r in assets}
    for r in assets:assert sha(menu[r['entry']])==r['sha256']
    layout=json.loads((W/'layout/NATIVE_CELL_VALIDATION.json').read_text())
    for r in layout['entries']:
        raw=(W/'layout'/f"entry_{r['entry']:02d}_native_cells.xet").read_bytes();assert sha(raw)==r['output_sha256'];menu[r['entry']]=raw
    summaries=[];all_changes=[];same=[];counts={'titles':0,'reward_names':0,'menu_atlases':0}
    for rel,b in baseline.items():
        source=W/'baseline'/rel;assert sha(source.read_bytes())==b['sha256']
        assert sha((ROOT/rel).read_bytes())==b['sha256'],'Live drift: '+rel
        arc=A.parse_arc(source);repl={};reasons={}
        for e in arc.entries:
            raw=A.unpack(e);key=e.name.split('\\')[-1].lower()
            if e.name in title_map:repl[e.index]=title_map[e.name];reasons[e.index]='titles'
            if '/quest/' in rel and key in reward_map:repl[e.index]=reward_map[key];reasons[e.index]='reward_names'
            if rel.endswith('/quest/menu.arc') and e.index in menu:repl[e.index]=menu[e.index];reasons[e.index]='menu_atlases'
            if e.index in repl:
                new=repl[e.index];assert raw[:20]==new[:20] and len(raw)==len(new) and xet_info(raw)==xet_info(new)
        if not repl:same.append(rel);continue
        data=A.rebuild(arc,repl);dest=STAGE/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        out=A.parse_arc(dest);assert (out.magic,out.version,len(out.entries))==(arc.magic,arc.version,len(arc.entries))
        changed=[];preserved=0
        for old,new in zip(arc.entries,out.entries):
            assert (old.name,old.type_hash,old.raw_size,old.flags)==(new.name,new.type_hash,new.raw_size,new.flags)
            if old.index in repl:
                assert A.unpack(new)==repl[old.index]
                changed.append(old.index);counts[reasons[old.index]]+=1
                all_changes.append({'archive':rel,'entry':old.index,'name':old.name,'category':reasons[old.index],
                                    'before_sha256':sha(A.unpack(old)),'after_sha256':sha(A.unpack(new))})
            else:assert old.compressed==new.compressed;preserved+=1
        summaries.append({'path':rel,'source_sha256':b['sha256'],'output_sha256':sha(data),'entries':len(out.entries),'changed_entries':changed,'preserved_compressed_resources':preserved})
    assert counts=={'titles':93,'reward_names':161,'menu_atlases':5},counts
    assert len(summaries)==34 and not same
    manifest={'status':'offline_validation_pass_runtime_required','created_utc':datetime.now(timezone.utc).isoformat(),
        'name':NAME,'counts':counts,'archives_changed':len(summaries),'resource_changes':len(all_changes),
        'all_lsp_and_other_untouched_compressed_resources_preserved':True,'xet_headers_and_dimensions_preserved':True,
        'internal_namespace_preserved':True,'excluded_dialogue_and_conquest_messages_modified':False,
        'runtime':'Not performed. Cold-boot check of quest list, difficulty, rewards, count and cleared list required.',
        'archives':summaries,'changes':all_changes}
    (STAGE/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    (STAGE/'README.txt').write_text('''Utage Quest Menu V2 - fit and reward corrections

Install by merging PS3_GAME into your current patched game root, overwriting the
included files. This is an additive menu update, not a full-game translation.

Fixes:
- All 31 quest titles fit the native 360x64 sampled cells, with ink height <=28px.
  Both rows and all copies in quest/qNNN_id, quest/quest_id and select/c_common agree.
- English QUESTS heading and Select a battle location instruction.
- Difficulty and fastest-time labels fit their exact native cells.
- Original filled-star, five-star underlay, reward-marker and slash blocks restored.
- Overlapping counter word removed, retaining selected/total numbers.
- 55 semantically mapped reward-name sheets, 161 archive-local copies, fitted to
  native name rows. The Miyoshi brothers retain Eldest/Middle/Youngest distinctions.
- English Z currency marker.

All LSPs, scripts, messages, portraits, other textures and unrelated compressed
resources are preserved. Claude's dialogue and tenka_msg000/001 files are excluded.
Shader-aware encoding preserves text-mask RGB even in transparent pixels.

Validation: archive/resource identities, untouched bytes, donor/mapping manifests,
texture headers and dimensions, native-cell crops, ZIP CRC and hashes passed.
Runtime is NOT verified: cold boot RPCS3 and check quest03, long titles, star values,
reward names and the 03/31 counter. Also check scrolling, cleared list and returns.

Rollback: sibling BACKUP_PRE_QUEST_MENU_V2.zip restores all34 pre-update archives.
Do not restore this backup over later changes to these same files.

Quest title wording is inherited from the English quest menu, including
SWORDSMAN'S DUEL. This release fixes the reported display defects.
''',encoding='utf-8')
    files={p.relative_to(STAGE).as_posix():sha(p.read_bytes()) for p in STAGE.rglob('*') if p.is_file()}
    assert len(files)==36
    with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in sorted(files):z.write(STAGE/rel,rel)
    with zipfile.ZipFile(ZIP) as z:
        assert z.testzip() is None and {n:sha(z.read(n)) for n in z.namelist()}==files
    report={**manifest,'package':str(ZIP),'package_sha256':sha(ZIP.read_bytes()),'package_bytes':ZIP.stat().st_size,
            'zip_crc_pass':True,'backup':str(W/'BACKUP_PRE_QUEST_MENU_V2.zip'),'installed':False}
    (W/'RELEASE_VALIDATION.json').write_text(json.dumps(report,indent=2))
    ZIP.with_suffix('.zip.sha256').write_text(report['package_sha256']+'  '+ZIP.name+'\n')
    print(json.dumps({k:report[k] for k in ('status','counts','archives_changed','resource_changes','package','package_sha256')},indent=2))
if __name__=='__main__':main()
