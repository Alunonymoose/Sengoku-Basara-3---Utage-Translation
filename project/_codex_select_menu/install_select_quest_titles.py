"""Install only the independently checked select archive, with a source guard."""
from pathlib import Path
import json, hashlib, shutil, zipfile
from datetime import datetime, timezone

WORK=Path(__file__).resolve().parent
ROOT=Path(r'E:\Utage Patching New')
REL=Path('PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc')
REPORT=WORK/'SELECT_QUEST_TITLES_V1_VALIDATION.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    report=json.loads(REPORT.read_text())
    audit=json.loads((WORK/'audit/INDEPENDENT_VALIDATION.json').read_text())
    assert audit['status']=='pass'
    package=Path(report['package'])
    assert sha(package.read_bytes())==report['package_sha256']==audit['package_sha256']
    target=ROOT/REL
    assert sha(target.read_bytes())==report['source_sha256'], 'Live source changed; refusing stale overwrite.'
    with zipfile.ZipFile(report['backup']) as z:
        assert z.testzip() is None and sha(z.read(REL.as_posix()))==report['source_sha256']
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        raw=z.read(REL.as_posix())
    assert sha(raw)==report['output_sha256']
    # A sibling temporary file allows the reviewed payload to replace the target in one operation.
    temporary=target.with_name('c_common.select_quest_v1.pending')
    assert not temporary.exists()
    temporary.write_bytes(raw)
    assert sha(temporary.read_bytes())==report['output_sha256']
    assert sha(target.read_bytes())==report['source_sha256']
    temporary.replace(target)
    assert sha(target.read_bytes())==report['output_sha256']
    report.update(installed=True,installed_path=str(target),installed_utc=datetime.now(timezone.utc).isoformat(),
                  installed_sha256=sha(target.read_bytes()),independent_validation=str(WORK/'audit/INDEPENDENT_VALIDATION.json'))
    REPORT.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ('installed','installed_path','installed_sha256','runtime_test')},indent=2))

if __name__=='__main__':main()
