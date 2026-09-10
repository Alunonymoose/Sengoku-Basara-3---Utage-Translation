from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

import arc_tools


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")
BASE_ZIP = Path(r"C:\Users\aluna\Downloads\Utage_Retry_English_V5_CUMULATIVE_ROOT_READY.zip")
BASE_ZIP_SHA256 = "238ad7abbd82f3e6683623f9ffb4521178d3d600989b2ad3be5430df83810596"
RELEASE_NAME = "Utage_Retry_English_V6_CUMULATIVE_ROOT_READY"
RELEASE_DIR = ROOT / RELEASE_NAME
OUTPUT_ZIP = ROOT / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = ROOT / f"{RELEASE_NAME}.zip.sha256"
TARGET_REL = Path("PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/tenka_id.arc")
CURRENT_ROOT = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def outer_jpn_hits(path: Path) -> list[dict]:
    patterns = {
        "ascii_backslash": b"rom\\jpn\\",
        "ascii_slash": b"rom/jpn/",
        "utf16le_backslash": "rom\\jpn\\".encode("utf-16le"),
        "utf16be_backslash": "rom\\jpn\\".encode("utf-16be"),
    }
    hits = []
    try:
        archive = arc_tools.parse_arc(path)
        resources = [(entry.index, entry.name, arc_tools.unpack(entry)) for entry in archive.entries]
    except Exception:
        resources = [(-1, "whole_file", path.read_bytes())]
    for index, name, raw in resources:
        for encoding, pattern in patterns.items():
            offset = raw.find(pattern)
            if offset >= 0:
                hits.append({
                    "resource_index": index,
                    "resource": name,
                    "encoding": encoding,
                    "offset": offset,
                })
    return hits


def xet_changed_blocks(old: bytes, new: bytes) -> dict:
    if old[:4] != b"\0XET" or new[:4] != b"\0XET":
        raise ValueError("not an XET pair")
    if old[:20] != new[:20]:
        raise AssertionError("XET header changed")
    if len(old) != len(new):
        raise AssertionError("XET size changed")
    start = struct.unpack_from(">I", old, 16)[0]
    changed = [
        offset
        for offset in range(start, len(old), 16)
        if old[offset:offset + 16] != new[offset:offset + 16]
    ]
    return {
        "header_unchanged": True,
        "size_unchanged": True,
        "changed_bc3_blocks": len(changed),
        "first_changed_block_offset": changed[0] if changed else None,
        "last_changed_block_offset": changed[-1] if changed else None,
    }


def build_manifest(base_tenka: Path, output_tenka: Path, tenka_report: dict) -> dict:
    old_arc = arc_tools.parse_arc(base_tenka)
    new_arc = arc_tools.parse_arc(output_tenka)
    unchanged_compressed = all(
        old.compressed == new.compressed
        for old, new in zip(old_arc.entries, new_arc.entries)
        if old.index not in (56, 59, 67)
    )
    old_029, new_029 = arc_tools.unpack(old_arc.entries[56]), arc_tools.unpack(new_arc.entries[56])
    old_lsp, new_lsp = arc_tools.unpack(old_arc.entries[59]), arc_tools.unpack(new_arc.entries[59])
    old_005, new_005 = arc_tools.unpack(old_arc.entries[67]), arc_tools.unpack(new_arc.entries[67])
    lsp_diffs = [index for index, (left, right) in enumerate(zip(old_lsp, new_lsp)) if left != right]
    expected_lsp_ranges = [
        16 + node * 176 + 0x20 + byte
        for node in (108, 113, 118, 123, 128, 133, 137)
        for byte in range(4)
    ]
    if lsp_diffs != expected_lsp_ranges:
        raise AssertionError({"lsp_diffs": lsp_diffs, "expected": expected_lsp_ranges})

    dependency_paths = {
        "output_tenka_id.arc": output_tenka,
        "current_tenka.arc": CURRENT_ROOT / "rom/eng/tenka/tenka.arc",
        "current_free_stage.arc": CURRENT_ROOT / "rom/tenka/free_stage.arc",
    }
    dependency_audit = {}
    for label, path in dependency_paths.items():
        dependency_audit[label] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "explicit_outer_rom_jpn_hits": outer_jpn_hits(path),
        }

    return {
        "patch": "Utage Free Battle English and Bounds V6 (cumulative over Retry English V5)",
        "created": "2026-08-30",
        "base_zip": str(BASE_ZIP),
        "base_zip_sha256": BASE_ZIP_SHA256,
        "target_arc": TARGET_REL.as_posix(),
        "source_tenka_id_sha256": sha256_file(base_tenka),
        "output_tenka_id_sha256": sha256_file(output_tenka),
        "changes": tenka_report["edits"],
        "changed_resources": tenka_report["changed_resources"],
        "texture_verification": {
            "tenka_005_ID_HQ": xet_changed_blocks(old_005, new_005),
            "tenka_029_ID_HQ": xet_changed_blocks(old_029, new_029),
        },
        "layout_verification": {
            "resource": "id\\lsp\\jpn\\tenka\\tenka_00",
            "nodes": [108, 113, 118, 123, 128, 133, 137],
            "scale_x_before": 0.70,
            "scale_x_after": 0.54,
            "scale_y": 0.88,
            "only_expected_scale_bytes_changed": True,
            "changed_raw_byte_offsets": lsp_diffs,
        },
        "dependency_audit": dependency_audit,
        "preserved": (
            "All V5 cumulative files; all tenka_id.arc resources except indices 56, 59, and 67; "
            "ARC entry order, type hashes, flags, internal jpn resource keys, XET headers, and XET sizes."
        ),
        "verification": {
            "status": "pass",
            "arc_entries": len(new_arc.entries),
            "changed_resource_indices": [56, 59, 67],
            "untouched_compressed_blobs_byte_identical": unchanged_compressed,
            "all_resources_unpack": True,
            "engine_smoke_test": "required",
        },
    }


def main() -> None:
    if sha256_file(BASE_ZIP) != BASE_ZIP_SHA256:
        raise AssertionError("V5 ZIP hash mismatch")
    if RELEASE_DIR.exists():
        if RELEASE_DIR.parent != ROOT or RELEASE_DIR.name != RELEASE_NAME:
            raise AssertionError(RELEASE_DIR)
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    with zipfile.ZipFile(BASE_ZIP) as archive:
        base_names = archive.namelist()
        if archive.testzip() is not None:
            raise AssertionError("V5 ZIP integrity failure")
        archive.extractall(RELEASE_DIR)

    base_tenka = RELEASE_DIR / TARGET_REL
    if sha256_file(base_tenka) != "dba81ec463dcf1d823a5c92fa33bab4501e253b9babd0bf41e821bd1c73eea17":
        raise AssertionError("unexpected V5 tenka_id.arc")
    shutil.copy2(ROOT / "tenka_id_v6.arc", base_tenka)

    tenka_report = json.loads((ROOT / "V6_TENKA_VALIDATION.json").read_text(encoding="utf-8"))
    manifest = build_manifest(
        ROOT / "_v5_tenka_id_for_manifest.arc",
        base_tenka,
        tenka_report,
    )
    manifest_path = RELEASE_DIR / "FREE_BATTLE_V6_MANIFEST_2026-08-30.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validation_path = RELEASE_DIR / "FREE_BATTLE_V6_VALIDATION_2026-08-30.json"
    validation_path.write_text(json.dumps(tenka_report, indent=2), encoding="utf-8")

    readme = """Sengoku BASARA 3 Utage English Patch — Free Battle English and Bounds V6

This package is cumulative over Retry English V5. Merge the included PS3_GAME folder into the current extracted Utage game root and overwrite when prompted. Do not reinstall an older patch afterward.

New V6 repair in rom/eng/tenka/tenka_id.arc:
- Free Battle header: 自由合戦 -> Quick Battles.
- Battle-count suffix: 合戦 -> Battles.
- Seven dynamic stage-name nodes: scaleX 0.70 -> 0.54; scaleY remains 0.88 so long official English stage names fit the Utage row art.

The Utage archive structure and internal id\\...\\jpn keys are preserved. Only three resources inside tenka_id.arc changed; every other V5 file and every other archive resource remain unchanged.

Offline archive, dependency-route, texture-header, resource-count, ZIP-integrity, and checksum checks pass. RPCS3/game-engine smoke testing is still required.
"""
    (RELEASE_DIR / "README_FREE_BATTLE_V6.txt").write_text(readme, encoding="utf-8")

    test_first = """Sengoku BASARA 3 Utage English Patch — V6 TEST FIRST

1. Fully close RPCS3.
2. Merge the included PS3_GAME folder into the current extracted Utage game root and overwrite.
3. Cold boot the game; do not use a save-state made before installation.
4. Open Quick Battles / Free Battle.
5. Confirm the top-left header reads Quick Battles.
6. Confirm the counter reads like 06/38 Battles.
7. Scroll through the list and confirm the longest names, especially Siege of Hasedo Castle, stay inside every row without clipping.
8. Regression-check the V5 Retry screen and the V3 Nobunaga faction route.

If anything is misplaced, keep the screenshot and report the exact screen. The package is offline-validated but cannot be marked runtime-confirmed until this cold-boot test passes.
"""
    (RELEASE_DIR / "README_TEST_FIRST.txt").write_text(test_first, encoding="utf-8")

    files = sorted(path for path in RELEASE_DIR.rglob("*") if path.is_file())
    expected_file_count = len(base_names) + 3
    if len(files) != expected_file_count:
        raise AssertionError({"files": len(files), "expected": expected_file_count})
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(RELEASE_DIR).as_posix())
    with zipfile.ZipFile(OUTPUT_ZIP) as archive:
        bad_member = archive.testzip()
        zip_names = archive.namelist()
    if bad_member is not None or len(zip_names) != expected_file_count:
        raise AssertionError({"bad_member": bad_member, "zip_files": len(zip_names)})

    zip_sha = sha256_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_sha}  {OUTPUT_ZIP.name}\n", encoding="ascii")
    package_report = {
        "status": "pass",
        "release_dir": str(RELEASE_DIR),
        "zip": str(OUTPUT_ZIP),
        "zip_sha256": zip_sha,
        "zip_file_count": len(zip_names),
        "base_file_count": len(base_names),
        "new_metadata_files": 3,
        "target_arc_sha256": sha256_file(base_tenka),
        "manifest": str(manifest_path),
        "dependency_outer_jpn_hit_count": sum(
            len(item["explicit_outer_rom_jpn_hits"])
            for item in manifest["dependency_audit"].values()
        ),
        "runtime_test": "required",
    }
    (ROOT / "V6_PACKAGE_VALIDATION.json").write_text(
        json.dumps(package_report, indent=2), encoding="utf-8"
    )
    print(json.dumps(package_report, indent=2))


if __name__ == "__main__":
    main()
