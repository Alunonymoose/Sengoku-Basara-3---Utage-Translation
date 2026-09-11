from __future__ import annotations
import base64, hashlib, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / 'v35_payload'
DIST = ROOT / 'dist-v35'
WORK = ROOT / '.build-v35-ci'
EXE = DIST / 'Alrummi3_2.0_studio.exe'
V4_SHA = '0050ed4af1ac958b5e0b4a117e9da73cfc89f61d0b26ccb23f1d38eefb7556f2'
RECOVERED = {
    'drive_bridge.pyc': '79245593fddd2b37d9b8f8c4275f75a7be6b2d8551d73550930d215b0ce4729a',
    'v4_mttex_codec.pyc': '424bec12062d6a8de1f814ac45e4eabd6adbb5fe1be3ce33f714ed24b3b34bdb',
    'v4_image_edit.pyc': '47a3b1f03d4c61b1e7068b4782dbb80675f8cb7015ec97667a150e948f731ca0',
    'v41_image_edit.pyc': 'c4937a515dd693805d7bcc05d9b18ba9c902f0044440d4092f6738fae5e593f8',
    'v41_donor_validate.pyc': 'b2ddcb429ead3fbb028e1c060f3c67e0c25e8cc659740c4914e8b33cab6dc970',
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def run(args):
    print('>', ' '.join(map(str,args)), flush=True)
    subprocess.run([str(a) for a in args], check=True)

def decode_payloads():
    parts = sorted(PAYLOAD.glob('alrummi3_v4.py.b64.part*'))
    if not parts:
        raise SystemExit('v35 alrummi3_v4 payload missing')
    v4 = base64.b64decode(''.join(p.read_text(encoding='ascii') for p in parts))
    if sha(v4) != V4_SHA:
        raise SystemExit('alrummi3_v4.py checksum mismatch')
    (ROOT/'alrummi3_v4.py').write_bytes(v4)
    for name, digest in RECOVERED.items():
        src = PAYLOAD/(name+'.b64')
        data = base64.b64decode(src.read_text(encoding='ascii'))
        if sha(data) != digest:
            raise SystemExit(f'{name} checksum mismatch')
        (ROOT/name).write_bytes(data)

def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(f'v35 build requires Python 3.11, got {sys.version}')
    os.chdir(ROOT)
    decode_payloads()
    run([sys.executable,'-m','py_compile','alrummi3_v4.py','alrummi3_v41.py'])
    run([sys.executable,'-c','import drive_bridge,v4_mttex_codec,v4_image_edit,v41_image_edit,v41_donor_validate; print("recovered imports: PASS")'])
    run([sys.executable,'-c','import alrummi3_v4,alrummi3_v41; print("v35 GUI imports: PASS")'])
    try:
        import PyInstaller
    except Exception as exc:
        raise SystemExit(f'PyInstaller missing: {exc}')
    roots=[Path(sys.base_prefix),Path(sys.prefix)]
    source_tcl=next((r/'tcl'/'tcl8.6' for r in roots if (r/'tcl'/'tcl8.6'/'init.tcl').is_file()),None)
    source_tk=next((r/'tcl'/'tk8.6' for r in roots if (r/'tcl'/'tk8.6'/'tk.tcl').is_file()),None)
    tcl_dll=next((r/'DLLs'/'tcl86t.dll' for r in roots if (r/'DLLs'/'tcl86t.dll').is_file()),None)
    tk_dll=next((r/'DLLs'/'tk86t.dll' for r in roots if (r/'DLLs'/'tk86t.dll').is_file()),None)
    if not all((source_tcl,source_tk,tcl_dll,tk_dll)):
        raise SystemExit('Could not locate Tcl/Tk')
    runtime=ROOT/'.tk-runtime-ci'; runtime.mkdir(exist_ok=True)
    for src,dst in ((source_tcl,runtime/'tcl8.6'),(source_tk,runtime/'tk8.6')):
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(src,dst)
    os.environ['TCL_LIBRARY']=str(runtime/'tcl8.6')
    os.environ['TK_LIBRARY']=str(runtime/'tk8.6')
    DIST.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onefile',
          '--name','Alrummi3_2.0_studio','--distpath',DIST,'--workpath',WORK,'--specpath',ROOT,
          '--runtime-tmpdir',r'.\Alrummi3_runtime',
          '--hidden-import','tkinter','--hidden-import','_tkinter',
          '--hidden-import','v4_mttex_codec','--hidden-import','v4_image_edit',
          '--hidden-import','v41_donor_validate','--hidden-import','v41_image_edit',
          '--hidden-import','alrummi3_v4','--hidden-import','drive_bridge',
          '--hidden-import','alrummi3_gui','--hidden-import','ai_extensions.api',
          '--hidden-import','ai_extensions.registry','--collect-data','rapidocr_onnxruntime',
          '--hidden-import','onnxruntime','--add-binary',f'{tcl_dll};.','--add-binary',f'{tk_dll};.',
          ROOT/'alrummi3_v41.py']
    run(args)
    if not EXE.is_file(): raise SystemExit('studio EXE missing after build')
    for dirname in ('ai_extensions','updates','project_data'):
        src,dst=ROOT/dirname,DIST/dirname
        if src.is_dir(): shutil.copytree(src,dst,dirs_exist_ok=True)
    for filename in ('donor_index.json','character_map.json','local_index.json'):
        src=ROOT/filename
        if src.is_file(): shutil.copy2(src,DIST/filename)
    print('BUILT',EXE)

if __name__=='__main__': main()
