"""Source-safe installer for the Alrummi3 v31 Drive factory bridge.

Designed for the user's newer local v31 tree, whose exact module filename may
not match the older GitHub copy. The installer discovers the GUI source by the
TWO visible button labels rather than by filename, makes a timestamped backup,
and injects a tiny startup hook only.

It never touches ARC/game files and never deletes the existing ChatGPT export
or import implementation.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys


MARKER_BEGIN = "# >>> ALRUMMI3_V31_DRIVE_FACTORY_BRIDGE >>>"
MARKER_END = "# <<< ALRUMMI3_V31_DRIVE_FACTORY_BRIDGE <<<"
NEEDLES = ("SEND TO CHATGPT", "IMPORT CHATGPT RESULT")
BRIDGE_FILES = ("v31_drive_bridge.py", "chatgpt_web_handoff.py")


class InstallError(RuntimeError):
    pass


def discover_gui_sources(root: Path) -> list[Path]:
    candidates: list[tuple[int, Path]] = []
    for path in root.glob("*.py"):
        if path.name in {Path(__file__).name, *BRIDGE_FILES}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if all(needle.casefold() in text.casefold() for needle in NEEDLES):
            try:
                stat = path.stat()
                score = int(stat.st_mtime_ns) + stat.st_size
            except OSError:
                score = 0
            candidates.append((score, path))
    candidates.sort(reverse=True, key=lambda item: item[0])
    return [path for _score, path in candidates]


def _find_mainloop_line(text: str) -> tuple[int, str] | None:
    lines = text.splitlines()
    pattern = re.compile(r"^(?P<indent>\s*)(?P<obj>[A-Za-z_][\w.]*)\.mainloop\s*\(\s*\)\s*(?:#.*)?$")
    found: tuple[int, str] | None = None
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            found = (index, match.group("obj"))
    return found


def build_hook(indent: str, app_expr: str) -> list[str]:
    return [
        indent + MARKER_BEGIN,
        indent + "def _install_alrummi3_drive_factory_bridge():",
        indent + "    try:",
        indent + "        from v31_drive_bridge import install_v31_drive_bridge",
        indent + "        from chatgpt_web_handoff import (",
        indent + "            attach_handoff, pick_handoff_pngs, read_handoff_prompt, ChatGPTHandoffError,",
        indent + "        )",
        indent + f"        _bridge = install_v31_drive_bridge({app_expr})",
        indent + f"        {app_expr}._alrummi3_drive_factory_bridge = _bridge",
        indent + "        _original_send = _bridge.send_to_factory",
        indent + "        def _send_with_real_attachments():",
        indent + "            _original_send()",
        indent + "            _job = getattr(_bridge, 'current_job', None)",
        indent + "            if _job is None:",
        indent + "                return",
        indent + "            try:",
        indent + "                _files = pick_handoff_pngs(_job.local_pack)",
        indent + "                _prompt = read_handoff_prompt(_job.local_pack)",
        indent + "                attach_handoff(files=_files, prompt=_prompt)",
        indent + "                try:",
        indent + f"                    {app_expr}._set_status('ChatGPT opened with real PNG attachments; review and press Send')",
        indent + "                except Exception:",
        indent + "                    pass",
        indent + "            except ChatGPTHandoffError as _attach_exc:",
        indent + "                print(f'[Alrummi3 ChatGPT Attach] {_attach_exc}')",
        indent + "                try:",
        indent + f"                    {app_expr}._set_status(f'Attachment handoff failed: {{_attach_exc}}')",
        indent + "                except Exception:",
        indent + "                    pass",
        indent + "        if getattr(_bridge, 'send_button', None) is not None:",
        indent + "            _bridge.send_button.configure(command=_send_with_real_attachments)",
        indent + "    except Exception as _drive_bridge_exc:",
        indent + "        print(f'[Alrummi3 Drive Bridge] not enabled: {_drive_bridge_exc}')",
        indent + f"{app_expr}.after(400, _install_alrummi3_drive_factory_bridge)",
        indent + MARKER_END,
    ]


def patch_source(path: Path, *, dry_run: bool = False) -> tuple[Path | None, bool]:
    text = path.read_text(encoding="utf-8", errors="strict")
    if MARKER_BEGIN in text:
        return None, False

    result = _find_mainloop_line(text)
    if result is None:
        raise InstallError(
            f"{path.name} contains the v31 ChatGPT buttons but no simple app.mainloop() call was found. No source was changed."
        )
    line_index, app_expr = result
    lines = text.splitlines()
    mainloop_line = lines[line_index]
    indent = mainloop_line[: len(mainloop_line) - len(mainloop_line.lstrip())]
    hook = build_hook(indent, app_expr)
    new_lines = lines[:line_index] + hook + [mainloop_line] + lines[line_index + 1 :]
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")

    if dry_run:
        return None, True

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.pre_drive_bridge_{stamp}.bak")
    shutil.copy2(path, backup)
    try:
        path.write_text(new_text, encoding="utf-8")
        compile(new_text, str(path), "exec")
    except Exception:
        shutil.copy2(backup, path)
        raise
    return backup, True


def verify_bridge_modules(root: Path) -> tuple[Path, Path]:
    bridge = root / "v31_drive_bridge.py"
    handoff = root / "chatgpt_web_handoff.py"
    for path in (bridge, handoff):
        if not path.is_file():
            raise InstallError(f"Missing {path.name}. Copy it beside this installer/source tree first.")
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    return bridge, handoff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Alrummi3 v31 Google Drive + real ChatGPT attachment bridge")
    parser.add_argument("root", nargs="?", default=".", help="Alrummi3 source folder")
    parser.add_argument("--source", help="Explicit GUI .py source instead of auto-discovery")
    parser.add_argument("--dry-run", action="store_true", help="Discover/validate but change nothing")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise InstallError(f"Not a directory: {root}")
    bridge, handoff = verify_bridge_modules(root)

    if args.source:
        source = Path(args.source)
        if not source.is_absolute():
            source = root / source
        source = source.resolve()
        if not source.is_file():
            raise InstallError(f"GUI source not found: {source}")
    else:
        candidates = discover_gui_sources(root)
        if not candidates:
            raise InstallError(
                "No top-level Python source containing both 'SEND TO CHATGPT' and 'IMPORT CHATGPT RESULT' was found. No source was changed."
            )
        source = candidates[0]
        if len(candidates) > 1:
            print("Detected possible GUI sources:")
            for index, path in enumerate(candidates, 1):
                mark = "  <-- selected" if index == 1 else ""
                print(f"  {index}. {path.name}{mark}")

    backup, changed = patch_source(source, dry_run=args.dry_run)
    print(f"Drive bridge:   {bridge}")
    print(f"Attach helper:  {handoff}")
    print(f"GUI source:     {source}")
    if args.dry_run:
        print("DRY RUN: startup hook can be inserted; no file changed.")
    elif not changed:
        print("Already installed; no source change required.")
    else:
        print(f"Installed. Backup: {backup}")
        print("Next launch wraps SEND with Drive queue + real ChatGPT browser attachments.")
        print("On first use, sign in once in the dedicated Alrummi3 Chrome/Edge profile.")
        print("The prompt is filled but never auto-submitted; review it and press Send yourself.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
