from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

APP_ROOT = Path(__file__).resolve().parent
DIST = APP_ROOT / "dist-hybrid"
WORK = APP_ROOT / ".build-hybrid"
EXE = DIST / "Alrummi3_Hybrid.exe"


def fail(message: str) -> None:
    print()
    print("=" * 64)
    print("BUILD FAILED")
    print("=" * 64)
    print(message)
    raise SystemExit(1)


def run(cmd) -> None:
    print(">", " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd)
    if result.returncode:
        fail(f"Command failed with exit code {result.returncode}")


def main() -> None:
    os.chdir(APP_ROOT)
    print("=" * 64)
    print("Alrummi 3 Hybrid - Python builder")
    print("=" * 64)

    required = [
        "alrummi3_hybrid.py",
        "alrummi3_gui.py",
        "mttex_codec.py",
        "openai_image_edit.py",
        "bcn.py",
    ]
    missing = [name for name in required if not (APP_ROOT / name).is_file()]
    if missing:
        fail("Missing required files:\n  " + "\n  ".join(missing))

    print("\n1/6  Syntax checks")
    run([
        sys.executable, "-m", "py_compile",
        "alrummi3_hybrid.py", "mttex_codec.py", "openai_image_edit.py",
    ])
    print("      PASS")

    print("\n2/6  Runtime regressions")
    import mttex_codec as m
    x = m.MtTexInfo(0x97, 0, 0, 1, 512, 256, 1, 0x2A, "DXT5", 0, (20,))
    d = x.as_dict()
    assert d["version"] == "0x97"
    assert d["format_code"] == "0x2A"
    assert d["display_shader"] == "MT YCbCr"
    importlib.import_module("alrummi3_hybrid")
    print("      codec metadata: PASS")
    print("      hybrid import:  PASS")

    try:
        import PyInstaller  # noqa: F401
    except Exception:
        fail(f"PyInstaller is not installed. Run: {sys.executable} -m pip install pyinstaller")

    print("\n3/6  Staging Tcl/Tk")
    python_root = Path(sys.base_prefix)
    prefixes = [python_root, Path(sys.prefix)]
    source_tcl = next((p / "tcl" / "tcl8.6" for p in prefixes if (p / "tcl" / "tcl8.6" / "init.tcl").is_file()), None)
    source_tk = next((p / "tcl" / "tk8.6" for p in prefixes if (p / "tcl" / "tk8.6" / "tk.tcl").is_file()), None)
    tcl_dll = next((p / "DLLs" / "tcl86t.dll" for p in prefixes if (p / "DLLs" / "tcl86t.dll").is_file()), None)
    tk_dll = next((p / "DLLs" / "tk86t.dll" for p in prefixes if (p / "DLLs" / "tk86t.dll").is_file()), None)
    if not all((source_tcl, source_tk, tcl_dll, tk_dll)):
        fail(f"Could not locate Python Tcl/Tk runtime. Python: {sys.executable}")

    tk_runtime = APP_ROOT / ".tk-runtime"
    target_tcl = tk_runtime / "tcl8.6"
    target_tk = tk_runtime / "tk8.6"
    tk_runtime.mkdir(parents=True, exist_ok=True)
    for src, dst in ((source_tcl, target_tcl), (source_tk, target_tk)):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    os.environ["TCL_LIBRARY"] = str(target_tcl)
    os.environ["TK_LIBRARY"] = str(target_tk)
    print("      PASS")

    print("\n4/6  Closing previous Hybrid build")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", "Alrummi3_Hybrid.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    time.sleep(0.7)
    if EXE.exists():
        try:
            EXE.unlink()
        except PermissionError:
            fail(f"Windows still has this file locked:\n{EXE}")
    print("      PASS")

    print("\n5/6  PyInstaller build")
    DIST.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "Alrummi3_Hybrid",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(APP_ROOT),
        "--runtime-tmpdir", r".\Alrummi3_runtime",
        "--hidden-import", "tkinter",
        "--hidden-import", "_tkinter",
        "--hidden-import", "mttex_codec",
        "--hidden-import", "openai_image_edit",
        "--hidden-import", "alrummi3_gui",
        "--hidden-import", "ai_extensions.api",
        "--hidden-import", "ai_extensions.registry",
        "--collect-data", "rapidocr_onnxruntime",
        "--hidden-import", "onnxruntime",
        "--add-binary", f"{tcl_dll};.",
        "--add-binary", f"{tk_dll};.",
        str(APP_ROOT / "alrummi3_hybrid.py"),
    ]
    run(cmd)
    if not EXE.is_file():
        fail(f"PyInstaller returned success but did not create:\n{EXE}")

    print("\n6/6  Copying runtime data")
    for dirname in ("ai_extensions", "updates", "chatgpt_jobs"):
        (DIST / dirname).mkdir(parents=True, exist_ok=True)
    for source_name in ("ai_extensions", "updates", "project_data"):
        src = APP_ROOT / source_name
        dst = DIST / source_name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
    for cache in ("donor_index.json", "character_map.json", "local_index.json"):
        src = APP_ROOT / cache
        if src.is_file():
            shutil.copy2(src, DIST / cache)

    print()
    print("=" * 64)
    print("SUCCESS")
    print("=" * 64)
    print(f"Built: {EXE}")


if __name__ == "__main__":
    main()
