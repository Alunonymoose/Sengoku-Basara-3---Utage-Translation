from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import arc_tools


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")
BASE = Path(r"C:\Users\aluna\Downloads\Utage_Retry_English_V5_CUMULATIVE_ROOT_READY.zip")
V6 = ROOT / "Utage_Retry_English_V6_CUMULATIVE_ROOT_READY.zip"
TARGET = "PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/tenka_id.arc"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    with zipfile.ZipFile(BASE) as base_zip, zipfile.ZipFile(V6) as v6_zip:
        if base_zip.testzip() is not None or v6_zip.testzip() is not None:
            raise AssertionError("ZIP CRC failure")
        base_names = set(base_zip.namelist())
        v6_names = set(v6_zip.namelist())
        added = sorted(v6_names - base_names)
        removed = sorted(base_names - v6_names)
        changed = sorted(
            name for name in base_names & v6_names if base_zip.read(name) != v6_zip.read(name)
        )
        if removed:
            raise AssertionError(removed)
        if changed != [TARGET, "README_TEST_FIRST.txt"]:
            raise AssertionError(changed)
        if added != [
            "FREE_BATTLE_V6_MANIFEST_2026-08-30.json",
            "FREE_BATTLE_V6_VALIDATION_2026-08-30.json",
            "README_FREE_BATTLE_V6.txt",
        ]:
            raise AssertionError(added)

        with tempfile.TemporaryDirectory(prefix="utage_v6_verify_") as temp:
            temp_root = Path(temp)
            v6_zip.extractall(temp_root)
            arc_files = sorted(temp_root.rglob("*.arc"))
            archive_entries = 0
            resource_count = 0
            for path in arc_files:
                archive = arc_tools.parse_arc(path)
                archive_entries += len(archive.entries)
                for entry in archive.entries:
                    raw = arc_tools.unpack(entry)
                    if len(raw) != entry.raw_size:
                        raise AssertionError((path, entry.index, len(raw), entry.raw_size))
                    resource_count += 1
            target_arc = arc_tools.parse_arc(temp_root / TARGET)
            if len(target_arc.entries) != 82:
                raise AssertionError(len(target_arc.entries))

    report = {
        "status": "pass",
        "zip": str(V6),
        "zip_sha256": digest(V6.read_bytes()),
        "zip_file_count": len(v6_names),
        "base_members_preserved": len(base_names) - len(changed),
        "changed_base_members": changed,
        "added_members": added,
        "removed_members": removed,
        "arc_file_count": len(arc_files),
        "arc_entry_count": archive_entries,
        "resource_unpack_count": resource_count,
        "tenka_id_entry_count": len(target_arc.entries),
        "runtime_test": "required",
    }
    (ROOT / "V6_INDEPENDENT_VALIDATION.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
