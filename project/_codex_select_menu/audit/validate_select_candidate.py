from pathlib import Path
import hashlib,json,struct,sys,zipfile
sys.path.insert(0,r'E:\Utage Patching New\_codex_tenka_v6')
import arc_tools as a

OUT=Path(__file__).parent
WORK=OUT.parent
LIVE=Path(r'E:\Utage Patching New')
REL=Path('PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc')
PACKAGE=WORK/'Utage_Select_Quest_Titles_V1_2026-09-08_ROOT_READY.zip'
def sha(b):return hashlib.sha256(b).hexdigest()
checks={}; details=[]
with zipfile.ZipFile(PACKAGE) as z:
    members=z.namelist()
    checks['zip_crc_pass']=z.testzip() is None
    arc_members=[n for n in members if n.lower().endswith('.arc')]
    checks['only_expected_archive']=arc_members==[REL.as_posix()]
    rebuilt=z.read(REL.as_posix())
path=OUT/'independent_candidate_c_common.arc'
path.write_bytes(rebuilt)
original=a.parse_arc(LIVE/REL)
candidate=a.parse_arc(path)
expected=set(range(31,62))
checks['archive_header_preserved']=original.data[:8]==candidate.data[:8]
checks['entry_count_76']=len(original.entries)==len(candidate.entries)==76
checks['metadata_names_types_flags_order']=all((x.index,x.name,x.type_hash,x.flags)==(y.index,y.name,y.type_hash,y.flags) for x,y in zip(original.entries,candidate.entries))
changed_raw=[];changed_compressed=[];donors_match=[];headers_match=[];untouched_raw=[];untouched_compressed=[];size_differences=[]
for old,new in zip(original.entries,candidate.entries):
    before=a.unpack(old);after=a.unpack(new)
    if before!=after:changed_raw.append(old.index)
    if old.compressed!=new.compressed:changed_compressed.append(old.index)
    if old.raw_size!=len(before) or new.raw_size!=len(after):
        size_differences.append(dict(index=old.index,name=old.name,before_declared=old.raw_size,before_actual=len(before),after_declared=new.raw_size,after_actual=len(after),preserved=old.raw_size==new.raw_size and before==after))
    if old.index in expected:
        n=old.index-31
        donor_path=LIVE/f'PS3_GAME/USRDIR/nativePS3/rom/eng/quest/q{n:03d}_id.arc'
        donor=a.parse_arc(donor_path)
        resource=donor.entries[0]
        donor_raw=a.unpack(resource)
        donors_match.append(after==donor_raw and resource.name==old.name)
        headers_match.append(before[:20]==after[:20])
        details.append(dict(index=old.index,name=old.name,source_sha256=sha(before),output_sha256=sha(after),donor_path=str(donor_path),donor_index=0,donor_sha256=sha(donor_raw)))
    else:
        untouched_raw.append(before==after)
        untouched_compressed.append(old.compressed==new.compressed)
checks['only_entries_31_through_61_changed_raw']=set(changed_raw)==expected
checks['only_entries_31_through_61_changed_compressed']=set(changed_compressed)==expected
checks['all_31_exact_donors']=all(donors_match) and len(donors_match)==31
checks['all_31_xet_headers_preserved']=all(headers_match)
checks['all_45_untouched_raw_preserved']=all(untouched_raw) and len(untouched_raw)==45
checks['all_45_untouched_compressed_preserved']=all(untouched_compressed)
checks['lsp_75_preserved_compressed']=original.entries[75].compressed==candidate.entries[75].compressed
checks['existing_declared_size_mismatches_preserved']=all(r['preserved'] for r in size_differences)
result=dict(status='pass' if all(checks.values()) else 'fail',package=str(PACKAGE),package_sha256=sha(PACKAGE.read_bytes()),package_bytes=PACKAGE.stat().st_size,members=members,original_arc_sha256=sha(original.data),candidate_arc_sha256=sha(candidate.data),checks=checks,changed_indices=changed_raw,existing_declared_size_mismatches=size_differences,mapping=details,runtime_test='required')
(OUT/'INDEPENDENT_VALIDATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='mapping'},indent=2))
if result['status']!='pass':raise SystemExit(1)
