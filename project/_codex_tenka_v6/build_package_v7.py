from __future__ import annotations

import hashlib
import json
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

import arc_tools


ROOT = Path(r"E:\Utage Patching New\_codex_tenka_v6")
BASE_ZIP = Path(r"C:\Users\aluna\Downloads\Utage_Retry_English_V6_CUMULATIVE_ROOT_READY.zip")
BASE_ZIP_SHA256 = "d7fadffe41d21baa782acdcfe8ece383030771b7abe8f2a75e3f73f91392c266"
BASE_TENKA_SHA256 = "eb2c1b46ff41fda29584ce070ce0cf78154d83e41f06c5583537a7dabe83c3de"
RELEASE_NAME = "Utage_Retry_English_V7_CUMULATIVE_ROOT_READY"
RELEASE_DIR = ROOT / RELEASE_NAME
OUTPUT_ZIP = ROOT / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = ROOT / f"{RELEASE_NAME}.zip.sha256"
DOWNLOAD_ZIP = Path(r"C:\Users\aluna\Downloads") / OUTPUT_ZIP.name
DOWNLOAD_SHA = Path(r"C:\Users\aluna\Downloads") / OUTPUT_SHA.name
TARGET = "PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/tenka_id.arc"
TARGET_REL = Path(TARGET)
STAGE_NODES = (108, 113, 118, 123, 128, 133, 137)
LSP_INDEX = 59
GEOMETRY_LEFT = -20
GEOMETRY_RIGHT = 20


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise AssertionError("resource size changed")
    return [index for index, (left, right) in enumerate(zip(before, after)) if left != right]


def patch_layout(raw: bytes) -> tuple[bytes, list[dict], list[int]]:
    if raw[:4] != b"\0PSL" or len(raw) != 66296:
        raise AssertionError("unexpected tenka_00 layout")
    output = bytearray(raw)
    records = []
    expected_changed = set()
    for node in STAGE_NODES:
        base = 16 + node * 176
        scale_x_offset = base + 0x20
        left_offset = base + 0x74
        right_offset = base + 0x7C
        before = {
            "scale_x": struct.unpack_from(">f", raw, scale_x_offset)[0],
            "scale_y": struct.unpack_from(">f", raw, base + 0x24)[0],
            "left": struct.unpack_from(">i", raw, left_offset)[0],
            "top": struct.unpack_from(">i", raw, base + 0x78)[0],
            "right": struct.unpack_from(">i", raw, right_offset)[0],
            "bottom": struct.unpack_from(">i", raw, base + 0x80)[0],
        }
        if not (abs(before["scale_x"] - 0.54) < 1e-6 and abs(before["scale_y"] - 0.88) < 1e-6):
            raise AssertionError({"node": node, "unexpected_scale": before})
        if (before["left"], before["top"], before["right"], before["bottom"]) != (-32, -16, 32, 16):
            raise AssertionError({"node": node, "unexpected_geometry": before})

        # V6 proved that non-uniform +0x20 edits are ignored by this dynamic
        # dummy_BM text path. Restore the retail value and instead narrow the
        # list-local glyph-quad template while preserving its vertical bounds.
        struct.pack_into(">f", output, scale_x_offset, 0.88)
        struct.pack_into(">i", output, left_offset, GEOMETRY_LEFT)
        struct.pack_into(">i", output, right_offset, GEOMETRY_RIGHT)
        for offset, size in ((scale_x_offset, 4), (left_offset, 4), (right_offset, 4)):
            for byte in range(size):
                if raw[offset + byte] != output[offset + byte]:
                    expected_changed.add(offset + byte)
        records.append({
            "node": node,
            "parent_row": f"7_0_{STAGE_NODES.index(node)}",
            "scale_x": {"before": before["scale_x"], "after": 0.88, "reason": "restore retail value after V6 runtime no-op"},
            "scale_y": {"before": before["scale_y"], "after": before["scale_y"]},
            "geometry": {
                "before": [before["left"], before["top"], before["right"], before["bottom"]],
                "after": [GEOMETRY_LEFT, before["top"], GEOMETRY_RIGHT, before["bottom"]],
                "horizontal_width_ratio": (GEOMETRY_RIGHT - GEOMETRY_LEFT) / (before["right"] - before["left"]),
            },
        })
    actual = changed_offsets(raw, bytes(output))
    if actual != sorted(expected_changed):
        raise AssertionError({"actual": actual, "expected": sorted(expected_changed)})
    return bytes(output), records, actual


def build_tenka(base_path: Path) -> tuple[Path, dict]:
    base = arc_tools.parse_arc(base_path)
    if len(base.entries) != 82:
        raise AssertionError("unexpected tenka_id entry count")
    old_lsp = arc_tools.unpack(base.entries[LSP_INDEX])
    new_lsp, records, raw_offsets = patch_layout(old_lsp)
    rebuilt_raw = arc_tools.rebuild(base, {LSP_INDEX: new_lsp})
    output_path = ROOT / "tenka_id_v7.arc"
    output_path.write_bytes(rebuilt_raw)
    rebuilt = arc_tools.parse_arc(output_path)

    changed_resources = []
    untouched_compressed = True
    for old, new in zip(base.entries, rebuilt.entries):
        old_raw = arc_tools.unpack(old)
        new_raw = arc_tools.unpack(new)
        if old_raw != new_raw:
            changed_resources.append({
                "index": new.index,
                "resource": new.name,
                "type_hash": f"0x{new.type_hash:08X}",
                "before_sha256": sha256_bytes(old_raw),
                "after_sha256": sha256_bytes(new_raw),
                "raw_size": len(new_raw),
            })
        elif old.compressed != new.compressed:
            untouched_compressed = False
    if [row["index"] for row in changed_resources] != [LSP_INDEX] or not untouched_compressed:
        raise AssertionError({"changed": changed_resources, "untouched_compressed": untouched_compressed})
    for protected in (56, 67):
        if base.entries[protected].compressed != rebuilt.entries[protected].compressed:
            raise AssertionError(f"protected V6 texture entry changed: {protected}")
    for entry in rebuilt.entries:
        arc_tools.unpack(entry)

    report = {
        "status": "pass",
        "patch": "Utage Free Battle Dynamic Stage Bounds V7",
        "created": "2026-08-30",
        "source_tenka_id_sha256": sha256_file(base_path),
        "output_tenka_id_sha256": sha256_bytes(rebuilt_raw),
        "entry_count": len(rebuilt.entries),
        "changed_resource_count": 1,
        "changed_resources": changed_resources,
        "layout_resource": "id\\lsp\\jpn\\tenka\\tenka_00",
        "layout_resource_index": LSP_INDEX,
        "stage_slots": records,
        "changed_lsp_raw_byte_offsets": raw_offsets,
        "universal_scope": "seven reusable St_s viewport slots covering all 38 Quick Battles stages",
        "preserved": [
            "V6 Quick Battles texture entry 67 byte-identical",
            "V6 Battles counter texture entry 56 byte-identical",
            "id_tenka GSM/FIM/TNF/CSA and every font atlas byte-identical",
            "right-side selected-stage title resources untouched",
            "all non-layout ARC compressed blobs byte-identical",
        ],
        "evidence": {
            "v6_runtime": "Quick Battles and Battles textures prove exact archive installed; shared names remained pixel-identical after scaleX 0.70 to 0.54.",
            "message_font": "id_tenka_r slots 104-141, FIM records, TNF, CSA, and active Latin pages are already correct and match official SH where counterparts exist.",
            "animation": "No animation records reference the seven St_s child IDs; no keyframe overwrites the attempted scale field.",
            "geometry": "St_s geometry is the list-local dynamic glyph-quad template; width changes 64 to 40 while height remains 32.",
        },
        "offline_validation": "pass",
        "engine_smoke_test": "required",
    }
    (ROOT / "V7_TENKA_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path, report


def build_package(tenka_path: Path, tenka_report: dict) -> dict:
    if sha256_file(BASE_ZIP) != BASE_ZIP_SHA256:
        raise AssertionError("V6 ZIP hash mismatch")
    if RELEASE_DIR.exists():
        if RELEASE_DIR.parent != ROOT or RELEASE_DIR.name != RELEASE_NAME:
            raise AssertionError(RELEASE_DIR)
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)
    with zipfile.ZipFile(BASE_ZIP) as base_zip:
        if base_zip.testzip() is not None:
            raise AssertionError("V6 ZIP CRC failure")
        base_names = base_zip.namelist()
        base_zip.extractall(RELEASE_DIR)
    target_path = RELEASE_DIR / TARGET_REL
    if sha256_file(target_path) != BASE_TENKA_SHA256:
        raise AssertionError("unexpected V6 tenka_id base")
    shutil.copy2(tenka_path, target_path)

    manifest = {
        **tenka_report,
        "base_zip": str(BASE_ZIP),
        "base_zip_sha256": BASE_ZIP_SHA256,
        "target_arc": TARGET,
        "supersedes": "V4/V6 stage-fit claims; their +0x20 horizontal-only edits were runtime-proven ineffective",
    }
    (RELEASE_DIR / "FREE_BATTLE_V7_MANIFEST_2026-08-30.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (RELEASE_DIR / "FREE_BATTLE_V7_VALIDATION_2026-08-30.json").write_text(json.dumps(tenka_report, indent=2), encoding="utf-8")
    readme = """Sengoku BASARA 3 Utage English Patch - Free Battle Dynamic Bounds V7

This is cumulative over V6. Merge PS3_GAME into the extracted game root and overwrite.

V6 runtime results:
- Quick Battles works.
- The counter suffix Battles works.
- The earlier horizontal-only St_s +0x20 edit did not affect dynamic stage text and is superseded here.

V7 changes only id\\lsp\\jpn\\tenka\\tenka_00 inside rom/eng/tenka/tenka_id.arc. It restores the seven failed +0x20 edits to retail 0.88 and narrows only the horizontal geometry of the seven reusable St_s list templates from 64 to 40 logical pixels. Vertical geometry remains 32. The seven slots render all 38 stage names, so the correction is universal across the scrolling list.

GSM, FIM, TNF, CSA, font atlases, Quick Battles, Battles, and the right-side selected-stage title are untouched. Offline ARC, resource, byte-scope, ZIP, and checksum validation pass. A cold-boot engine test is still required before runtime confirmation.
"""
    (RELEASE_DIR / "README_FREE_BATTLE_V7.txt").write_text(readme, encoding="utf-8")
    test = """Sengoku BASARA 3 Utage English Patch - V7 TEST FIRST

1. Fully close RPCS3.
2. Merge the included PS3_GAME folder into the extracted Utage game root and overwrite.
3. Cold boot; do not load a pre-install save-state.
4. Open Quick Battles.
5. Confirm Quick Battles and the nn/38 Battles counter remain correct.
6. Scroll all 38 stages through top, middle, and bottom list positions.
7. Check selected and unselected rows. Prioritize Dragon Assault on Ueda Castle and Siege of Hasedo Castle.
8. Confirm every list name stays inside the row and remains readable.
9. Confirm the large right-side selected-stage title is unchanged.
10. Regression-check Retry and Nobunaga's faction label.

If a name is still wide or becomes too narrow, send one screenshot showing it and the selected row. V7 is offline-validated; only this cold-boot test can confirm the proprietary dynamic renderer.
"""
    (RELEASE_DIR / "README_TEST_FIRST.txt").write_text(test, encoding="utf-8")

    files = sorted(path for path in RELEASE_DIR.rglob("*") if path.is_file())
    expected_count = len(base_names) + 3
    if len(files) != expected_count:
        raise AssertionError({"files": len(files), "expected": expected_count})
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, path.relative_to(RELEASE_DIR).as_posix())
    with zipfile.ZipFile(OUTPUT_ZIP) as output:
        if output.testzip() is not None or len(output.namelist()) != expected_count:
            raise AssertionError("V7 ZIP integrity failure")
    output_hash = sha256_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{output_hash}  {OUTPUT_ZIP.name}\n", encoding="ascii")
    shutil.copy2(OUTPUT_ZIP, DOWNLOAD_ZIP)
    shutil.copy2(OUTPUT_SHA, DOWNLOAD_SHA)
    return {
        "status": "pass",
        "release_dir": str(RELEASE_DIR),
        "zip": str(OUTPUT_ZIP),
        "download_zip": str(DOWNLOAD_ZIP),
        "zip_sha256": output_hash,
        "zip_file_count": expected_count,
        "base_file_count": len(base_names),
        "target_arc_sha256": sha256_file(target_path),
        "runtime_test": "required",
    }


def independent_verify(package_report: dict) -> dict:
    with zipfile.ZipFile(BASE_ZIP) as base_zip, zipfile.ZipFile(OUTPUT_ZIP) as v7_zip:
        if base_zip.testzip() is not None or v7_zip.testzip() is not None:
            raise AssertionError("ZIP CRC failure")
        base_names = set(base_zip.namelist())
        v7_names = set(v7_zip.namelist())
        added = sorted(v7_names - base_names)
        removed = sorted(base_names - v7_names)
        changed = sorted(name for name in base_names & v7_names if base_zip.read(name) != v7_zip.read(name))
        expected_added = [
            "FREE_BATTLE_V7_MANIFEST_2026-08-30.json",
            "FREE_BATTLE_V7_VALIDATION_2026-08-30.json",
            "README_FREE_BATTLE_V7.txt",
        ]
        if removed or added != expected_added or changed != [TARGET, "README_TEST_FIRST.txt"]:
            raise AssertionError({"added": added, "removed": removed, "changed": changed})
        base_arc = arc_tools.parse_arc(ROOT / "tenka_id_v6.arc")
        with tempfile.TemporaryDirectory(prefix="utage_v7_verify_") as temp:
            temp_root = Path(temp)
            v7_zip.extractall(temp_root)
            arc_files = sorted(temp_root.rglob("*.arc"))
            archive_entries = 0
            resources = 0
            warnings = []
            target_arc = None
            for path in arc_files:
                archive = arc_tools.parse_arc(path)
                archive_entries += len(archive.entries)
                relative = path.relative_to(temp_root).as_posix()
                if relative == TARGET:
                    target_arc = archive
                for entry in archive.entries:
                    raw = arc_tools.unpack(entry)
                    resources += 1
                    if len(raw) != entry.raw_size:
                        warning = {"archive": relative, "entry": entry.index, "resource": entry.name, "declared": entry.raw_size, "actual": len(raw)}
                        if relative == TARGET and entry.index == LSP_INDEX:
                            raise AssertionError(warning)
                        warnings.append(warning)
            if target_arc is None or len(target_arc.entries) != 82:
                raise AssertionError("target ARC missing")
            changed_resources = [
                new.index
                for old, new in zip(base_arc.entries, target_arc.entries)
                if arc_tools.unpack(old) != arc_tools.unpack(new)
            ]
            if changed_resources != [LSP_INDEX]:
                raise AssertionError(changed_resources)
    report = {
        "status": "pass",
        "zip": str(OUTPUT_ZIP),
        "zip_sha256": package_report["zip_sha256"],
        "zip_file_count": len(v7_names),
        "changed_base_members": changed,
        "added_members": added,
        "removed_members": removed,
        "arc_file_count": len(arc_files),
        "arc_entry_count": archive_entries,
        "resource_unpack_count": resources,
        "tenka_id_entry_count": len(target_arc.entries),
        "tenka_id_changed_resource_indices_vs_v6": changed_resources,
        "inherited_declared_size_warnings": warnings,
        "runtime_test": "required",
    }
    (ROOT / "V7_INDEPENDENT_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    if sha256_file(ROOT / "tenka_id_v6.arc") != BASE_TENKA_SHA256:
        raise AssertionError("local V6 ARC precondition changed")
    tenka_path, tenka_report = build_tenka(ROOT / "tenka_id_v6.arc")
    package_report = build_package(tenka_path, tenka_report)
    independent = independent_verify(package_report)
    (ROOT / "V7_PACKAGE_VALIDATION.json").write_text(json.dumps(package_report, indent=2), encoding="utf-8")
    print(json.dumps({"package": package_report, "independent_validation": independent}, indent=2))


if __name__ == "__main__":
    main()
