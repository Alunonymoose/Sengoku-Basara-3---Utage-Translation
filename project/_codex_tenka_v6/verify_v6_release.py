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
CHANGED_RESOURCE_INDICES = (56, 59, 67)


def main() -> None:
    with zipfile.ZipFile(BASE) as base_zip, zipfile.ZipFile(V6) as v6_zip:
        if base_zip.testzip() is not None or v6_zip.testzip() is not None:
            raise AssertionError("ZIP CRC failure")
        base_names, v6_names = set(base_zip.namelist()), set(v6_zip.namelist())
        added = sorted(v6_names - base_names)
        removed = sorted(base_names - v6_names)
        changed = sorted(
            name for name in base_names & v6_names if base_zip.read(name) != v6_zip.read(name)
        )
        if removed or changed != [TARGET, "README_TEST_FIRST.txt"]:
            raise AssertionError({"removed": removed, "changed": changed})
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
            archive_entries = resource_count = 0
            inherited_warnings = []
            target_arc = None
            for path in arc_files:
                relative = path.relative_to(temp_root).as_posix()
                archive = arc_tools.parse_arc(path)
                archive_entries += len(archive.entries)
                if relative == TARGET:
                    target_arc = archive
                for entry in archive.entries:
                    raw = arc_tools.unpack(entry)
                    resource_count += 1
                    if len(raw) == entry.raw_size:
                        continue
                    warning = {
                        "archive": relative,
                        "entry": entry.index,
                        "resource": entry.name,
                        "declared": entry.raw_size,
                        "actual": len(raw),
                    }
                    if relative == TARGET and entry.index in CHANGED_RESOURCE_INDICES:
                        raise AssertionError(warning)
                    inherited_warnings.append(warning)
            if target_arc is None or len(target_arc.entries) != 82:
                raise AssertionError("target ARC missing or wrong count")

    report = {
        "status": "pass",
        "zip": str(V6),
        "zip_sha256": hashlib.sha256(V6.read_bytes()).hexdigest(),
        "zip_file_count": len(v6_names),
        "unchanged_base_members": len(base_names) - len(changed),
        "changed_base_members": changed,
        "added_members": added,
        "removed_members": removed,
        "arc_file_count": len(arc_files),
        "arc_entry_count": archive_entries,
        "resource_unpack_count": resource_count,
        "tenka_id_entry_count": len(target_arc.entries),
        "modified_resource_declared_size_mismatches": 0,
        "inherited_declared_size_warnings": inherited_warnings,
        "runtime_test": "required",
    }
    (ROOT / "V6_INDEPENDENT_VALIDATION.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
