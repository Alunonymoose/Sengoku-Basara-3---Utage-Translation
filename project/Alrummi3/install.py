"""Install a built archive into the game tree, and take it back out again.

The project's own rule is that an offline audit proves nothing: after
installing you cold-boot RPCS3 and look at the screen.  That loop was being
closed by hand, copying files around, which is where a wrong file or a lost
original creeps in.

So installation here is one action with three guarantees:

* the original is copied to a timestamped backup **before** anything is
  overwritten, and the install refuses to proceed if that backup fails;
* a manifest records every install so it can be reverted exactly;
* the file being installed is parsed and checked to be a valid archive with
  the same entry count as the file it replaces, so a truncated or mismatched
  build cannot reach the game.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from alrummi3_core import parse_arc, sha256

BACKUP_DIR_NAME = "_alrummi3_backups"
MANIFEST_NAME = "install_manifest.json"


def backup_root(app_root: Path) -> Path:
    return Path(app_root) / BACKUP_DIR_NAME


def manifest_path(app_root: Path) -> Path:
    return backup_root(app_root) / MANIFEST_NAME


def load_manifest(app_root: Path) -> list[dict]:
    path = manifest_path(app_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_manifest(app_root: Path, entries: list[dict]) -> None:
    root = backup_root(app_root)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path(app_root).write_text(
        json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8"
    )


def check_compatible(new_file: Path, target: Path) -> dict:
    """Refuse anything that is not a plausible replacement for the target."""

    new_file = Path(new_file)
    target = Path(target)
    if not new_file.is_file():
        raise ValueError(f"nothing to install at {new_file}")
    built = parse_arc(new_file)
    report = {
        "entries": len(built.entries),
        "platform": built.platform,
        "version": built.version,
        "target_exists": target.is_file(),
    }
    if target.is_file():
        current = parse_arc(target)
        report["target_entries"] = len(current.entries)
        if len(current.entries) != len(built.entries):
            raise ValueError(
                f"entry count differs: the build has {len(built.entries)}, "
                f"the installed file has {len(current.entries)}. That is not a "
                "replacement for this archive."
            )
        if current.endian != built.endian or current.version != built.version:
            raise ValueError(
                "platform or version differs between the build and the target"
            )
    return report


def install(new_file: Path, target: Path, app_root: Path, *, note: str = "") -> dict:
    """Back up the target, then replace it. Returns the manifest entry."""

    new_file = Path(new_file)
    target = Path(target)
    report = check_compatible(new_file, target)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = backup_root(app_root) / stamp
    root.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.is_file():
        backup = root / target.name
        shutil.copy2(target, backup)
        if backup.stat().st_size != target.stat().st_size:
            raise ValueError("the backup did not copy completely; nothing was installed")

    payload = new_file.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    entry = {
        "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target": str(target),
        "source": str(new_file),
        "backup": str(backup) if backup else "",
        "sha256": sha256(payload),
        "entries": report["entries"],
        "note": note,
        "reverted": False,
    }
    entries = load_manifest(app_root)
    entries.append(entry)
    save_manifest(app_root, entries)
    return entry


def revert(entry_index: int, app_root: Path) -> dict:
    entries = load_manifest(app_root)
    if not 0 <= entry_index < len(entries):
        raise ValueError("no such install")
    entry = entries[entry_index]
    backup = Path(entry.get("backup", ""))
    target = Path(entry["target"])
    if not backup.is_file():
        raise ValueError(
            f"the backup is missing: {backup}. Nothing was changed."
        )
    shutil.copy2(backup, target)
    entry["reverted"] = True
    entry["reverted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_manifest(app_root, entries)
    return entry


def revert_all(app_root: Path) -> dict:
    entries = load_manifest(app_root)
    done = 0
    failed: list[str] = []
    # Newest first, so a file installed twice ends up at its oldest original.
    for index in range(len(entries) - 1, -1, -1):
        if entries[index].get("reverted"):
            continue
        try:
            revert(index, app_root)
            done += 1
        except Exception as exc:
            failed.append(f"{entries[index].get('target')}: {exc}")
    return {"reverted": done, "failed": failed}
