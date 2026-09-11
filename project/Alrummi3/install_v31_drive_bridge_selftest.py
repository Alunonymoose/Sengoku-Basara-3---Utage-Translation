"""Offline self-test for install_v31_drive_bridge.py.

Creates a fake v31-style GUI source in a temporary directory and verifies:
- label-based discovery
- dry-run leaves bytes unchanged
- real install creates a backup
- hook is inserted before mainloop
- patched source still compiles
- a second install is idempotent
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from install_v31_drive_bridge import (
    MARKER_BEGIN,
    discover_gui_sources,
    patch_source,
)


FAKE_SOURCE = '''import tkinter as tk\nfrom tkinter import ttk\n\nroot = tk.Tk()\n\n# These strings intentionally match the shipped v31 labels.\nttk.Button(root, text="SEND TO CHATGPT", command=lambda: None).pack()\nttk.Button(root, text="IMPORT CHATGPT RESULT…", command=lambda: None).pack()\n\nroot.mainloop()\n'''


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS  {name}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="alrummi3_bridge_install_test_") as temp:
        root = Path(temp)
        source = root / "alrummi3_v41.py"
        source.write_text(FAKE_SOURCE, encoding="utf-8")
        before = source.read_bytes()

        candidates = discover_gui_sources(root)
        check("discovers label-matched GUI source", candidates == [source])

        backup, changed = patch_source(source, dry_run=True)
        check("dry-run reports patchable", changed and backup is None)
        check("dry-run leaves source unchanged", source.read_bytes() == before)

        backup, changed = patch_source(source)
        check("real install changes source", changed)
        check("backup created", backup is not None and backup.is_file())
        check("backup is byte-identical original", backup.read_bytes() == before)

        patched = source.read_text(encoding="utf-8")
        check("marker inserted", MARKER_BEGIN in patched)
        check("hook precedes mainloop", patched.index(MARKER_BEGIN) < patched.index("root.mainloop()"))
        compile(patched, str(source), "exec")
        check("patched source compiles", True)

        first = source.read_bytes()
        backup2, changed2 = patch_source(source)
        check("second install is idempotent", not changed2 and backup2 is None)
        check("second install leaves bytes unchanged", source.read_bytes() == first)

    print("8/8 installer checks passed")


if __name__ == "__main__":
    main()
