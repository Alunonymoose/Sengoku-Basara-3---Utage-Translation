from pathlib import Path
from datetime import datetime,timezone
import struct,zlib,json,hashlib,zipfile,sys
W=Path(__file__).resolve().parent;ROOT=Path(r'E:\Utage Patching New')
sha=lambda r:hashlib.sha256(r).hexdigest()
def parse(data):
    assert data[:4]==b'\0CRA'
    version,count=struct.unpack_from('>HH',data,4);assert version==8
    rows=[]
    for n in range(count):
        p=8+n*80;rec=data[p:p+80];typ,csize,packed,offset=struct.unpack_from('>4I',rec,64)
        assert offset>=8+80*count and offset+csize<=len(data)
        blob=data[offset:offset+csize]
        try:raw=zlib.decompress(blob)
        except zlib.error:
            assert csize==packed>>3;raw=blob
        rows.append({'name':rec[:64],'type':typ,'packed':packed,'compressed':blob,'raw':raw})
    return rows
def main():
    report=json.loads((W/'RELEASE_VALIDATION.json').read_text());package=Path(report['package'])
    assert sha(package.read_bytes())==report['package_sha256']
    allowed={(r['archive'],r['entry']):r for r in report['changes']}
    before_manifest=json.loads((W/'BASELINE_MANIFEST.json').read_text())
    verified=[];kept=0;changed=0
    with zipfile.ZipFile(report['backup']) as b,zipfile.ZipFile(package) as z:
        assert b.testzip() is None and z.testzip() is None
        game=[n for n in z.namelist() if n.startswith('PS3_GAME/')]
        assert set(game)==set(before_manifest)
        for path in game:
            assert '/rom/eng/quest/' in path or path.endswith('/rom/eng/select/c_common.arc')
            old=b.read(path);new=z.read(path);assert sha(old)==before_manifest[path]['sha256']
            a,c=parse(old),parse(new);assert len(a)==len(c)
            for i,(left,right) in enumerate(zip(a,c)):
                assert (left['name'],left['type'],left['packed'])==(right['name'],right['type'],right['packed'])
                if (path,i) in allowed:
                    target=allowed[(path,i)]
                    assert sha(left['raw'])==target['before_sha256'] and sha(right['raw'])==target['after_sha256']
                    assert left['type']==0x241F5DEB and left['raw'][:20]==right['raw'][:20]
                    assert len(left['raw'])==len(right['raw']);changed+=1
                else:assert left['compressed']==right['compressed'];kept+=1
            verified.append({'path':path,'bytes':len(new),'sha256':sha(new)})
        assert changed==259 and len(verified)==34
        result={'status':'pass','archives':len(verified),'changed_textures':changed,'preserved_compressed_resources':kept,
                'all_metadata_and_resource_order_preserved':True,'all_non_texture_payloads_preserved':True,
                'zip_crc_pass':True,'package_sha256':report['package_sha256'],'runtime':'required'}
        (W/'INDEPENDENT_RELEASE_CHECK.json').write_text(json.dumps(result,indent=2))
        if '--install' in sys.argv:
            # Guard every target before changing any target. No dialogue/map messages are in this set.
            for path in game:assert sha((ROOT/path).read_bytes())==before_manifest[path]['sha256'],'Live drift: '+path
            temporary=[]
            for item in verified:
                dst=ROOT/item['path'];tmp=dst.with_name(dst.name+'.quest_v2_pending');assert not tmp.exists()
                data=z.read(item['path']);tmp.write_bytes(data);assert sha(tmp.read_bytes())==item['sha256']
                temporary.append((item,dst,tmp))
            for item,dst,tmp in temporary:
                assert sha(dst.read_bytes())==before_manifest[item['path']]['sha256'];tmp.replace(dst)
                assert sha(dst.read_bytes())==item['sha256']
            report.update(installed=True,installed_utc=datetime.now(timezone.utc).isoformat(),installed_files=verified,
                          independent_check=str(W/'INDEPENDENT_RELEASE_CHECK.json'))
            (W/'RELEASE_VALIDATION.json').write_text(json.dumps(report,indent=2))
            result['installed']=True
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()
