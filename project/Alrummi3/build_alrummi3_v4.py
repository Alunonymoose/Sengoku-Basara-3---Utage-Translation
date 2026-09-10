from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

APP_ROOT = Path(__file__).resolve().parent
DIST = APP_ROOT / "dist-v4"
WORK = APP_ROOT / ".build-v4"
EXE = DIST / "Alrummi3_V4.exe"

def fail(message: str):
    print("\n" + "="*64)
    print("BUILD FAILED")
    print("="*64)
    print(message)
    input("\nPress Enter to close...")
    raise SystemExit(1)

def run(args):
    print(">", " ".join(str(x) for x in args))
    result = subprocess.run(args)
    if result.returncode:
        fail(f"Command failed with exit code {result.returncode}")

def main():
    os.chdir(APP_ROOT)
    print("="*64)
    print("Alrummi 3 V4 - reliable builder")
    print("="*64)

    required = [
        "alrummi3_v4.py", "alrummi3_gui.py", "alrummi3_core.py",
        "v4_mttex_codec.py", "v4_image_edit.py", "bcn.py",
    ]
    missing = [x for x in required if not (APP_ROOT/x).is_file()]
    if missing:
        fail("Missing:\n  " + "\n  ".join(missing))

    print("\n1/5 Syntax/import preflight")
    run([sys.executable, "-m", "py_compile",
         "alrummi3_v4.py", "v4_mttex_codec.py", "v4_image_edit.py"])
    run([sys.executable, "-c",
         "import v4_mttex_codec as c; "
         "x=c.XetInfo(0x97,0,0,1,512,256,1,0x2A,'DXT5',0,(20,)); "
         "d=x.as_dict(); assert d['version']=='0x97'; "
         "assert d['format_code']=='0x2A'; assert d['display_shader']=='MT YCbCr'; "
         "import alrummi3_v4; print('V4 import regression: PASS')"])
    try:
        import PyInstaller  # noqa
    except Exception:
        fail(f'PyInstaller missing. Run:\n"{sys.executable}" -m pip install pyinstaller')

    print("\n2/5 Locate Tcl/Tk")
    roots = [Path(sys.base_prefix), Path(sys.prefix)]
    source_tcl = next((r/"tcl"/"tcl8.6" for r in roots if (r/"tcl"/"tcl8.6"/"init.tcl").is_file()), None)
    source_tk = next((r/"tcl"/"tk8.6" for r in roots if (r/"tcl"/"tk8.6"/"tk.tcl").is_file()), None)
    tcl_dll = next((r/"DLLs"/"tcl86t.dll" for r in roots if (r/"DLLs"/"tcl86t.dll").is_file()), None)
    tk_dll = next((r/"DLLs"/"tk86t.dll" for r in roots if (r/"DLLs"/"tk86t.dll").is_file()), None)
    if not all((source_tcl, source_tk, tcl_dll, tk_dll)):
        fail(f"Could not locate Tcl/Tk for {sys.executable}")

    runtime = APP_ROOT/".tk-runtime"
    target_tcl, target_tk = runtime/"tcl8.6", runtime/"tk8.6"
    runtime.mkdir(exist_ok=True)
    for src,dst in ((source_tcl,target_tcl),(source_tk,target_tk)):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src,dst)
    os.environ["TCL_LIBRARY"] = str(target_tcl)
    os.environ["TK_LIBRARY"] = str(target_tk)
    print("Tcl/Tk: PASS")

    print("\n3/5 Close old V4 if needed")
    if os.name == "nt":
        subprocess.run(["taskkill","/F","/IM","Alrummi3_V4.exe"],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    time.sleep(0.7)
    if EXE.exists():
        try:
            EXE.unlink()
        except PermissionError:
            fail(f"Windows still has {EXE} locked. Close it in Task Manager and retry.")

    print("\n4/5 Build")
    DIST.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "Alrummi3_V4",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(APP_ROOT),
        "--runtime-tmpdir", r".\Alrummi3_runtime",
        "--hidden-import", "tkinter",
        "--hidden-import", "_tkinter",
        "--hidden-import", "v4_mttex_codec",
        "--hidden-import", "v4_image_edit",
        "--hidden-import", "alrummi3_gui",
        "--hidden-import", "ai_extensions.api",
        "--hidden-import", "ai_extensions.registry",
        "--collect-data", "rapidocr_onnxruntime",
        "--hidden-import", "onnxruntime",
        "--add-binary", f"{tcl_dll};.",
        "--add-binary", f"{tk_dll};.",
        str(APP_ROOT/"alrummi3_v4.py"),
    ]
    run(args)
    if not EXE.is_file():
        fail(f"Build reported success but {EXE} does not exist.")

    print("\n5/5 Copy project runtime data")
    for dirname in ("ai_extensions","updates"):
        src, dst = APP_ROOT/dirname, DIST/dirname
        if src.is_dir():
            shutil.copytree(src,dst,dirs_exist_ok=True)
    src = APP_ROOT/"project_data"
    if src.is_dir():
        shutil.copytree(src,DIST/"project_data",dirs_exist_ok=True)
    for filename in ("donor_index.json","character_map.json","local_index.json"):
        src = APP_ROOT/filename
        if src.is_file():
            shutil.copy2(src,DIST/filename)

    print("\n"+"="*64)
    print("SUCCESS")
    print("="*64)
    print(EXE)
    if os.name == "nt":
        os.startfile(EXE)

if __name__ == "__main__":
    main()
