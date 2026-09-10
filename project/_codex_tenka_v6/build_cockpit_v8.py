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
LIVE = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")
SH = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom")
BASE_ZIP = Path(r"C:\Users\aluna\Downloads\Utage_Retry_English_V7_CUMULATIVE_ROOT_READY.zip")
BASE_ZIP_SHA = "84e4def0da1d452052fc0a9a710eb2bff5718740401df28096ae5dd450dfcdef"
RELEASE = "Utage_Retry_English_V8_CUMULATIVE_ROOT_READY"
RELEASE_DIR = ROOT / RELEASE
OUTPUT_ZIP = ROOT / f"{RELEASE}.zip"
OUTPUT_SHA = ROOT / f"{RELEASE}.zip.sha256"
DOWNLOAD_ZIP = Path(r"C:\Users\aluna\Downloads") / OUTPUT_ZIP.name
DOWNLOAD_SHA = Path(r"C:\Users\aluna\Downloads") / OUTPUT_SHA.name
REL1 = Path("PS3_GAME/USRDIR/nativePS3/rom/eng/id/cockpit1P.arc")
REL2 = Path("PS3_GAME/USRDIR/nativePS3/rom/eng/id/cockpit2P.arc")
DONOR_SHA = "b78df3541d43d133e761e218d0057d24782938f2fc0a61c35c7263fa6670a11b"
CLEAN_SHA = "7c2c7f681327c1a90619c15da03911c3f48e1fc04dabdedd1e362edb9b225da8"
BROKEN_SHA = "84eb67014a03a070755442cc204526956d67084b01a7b39716fc61ca36f3b209"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xet_dimensions(raw: bytes) -> tuple[int, int, int]:
    if raw[:4] != b"\0XET":
        raise AssertionError("not XET")
    packed = int.from_bytes(b"\0" + raw[8:11], "big")
    width = (packed & 0xFFF) * 4
    height = ((packed >> 12) & 0xFFF) * 2
    return width, height, struct.unpack_from(">I", raw, 16)[0]


def hybrid_atlas(clean: bytes, donor: bytes) -> tuple[bytes, dict]:
    if sha(clean) != CLEAN_SHA or sha(donor) != DONOR_SHA:
        raise AssertionError("cockpit texture precondition changed")
    clean_w, clean_h, clean_start = xet_dimensions(clean)
    donor_w, donor_h, donor_start = xet_dimensions(donor)
    if (clean_w, clean_h, donor_w, donor_h) != (128, 128, 128, 64):
        raise AssertionError((clean_w, clean_h, donor_w, donor_h))
    output = bytearray(clean)
    blocks_w = clean_w // 4
    changed_blocks = []
    # SH's Kill node samples logical/native BC3 slot [0,0,64,32]. Place
    # those exact blocks in Utage's unused [64,0,128,32] slot.
    for block_y in range(0, 32 // 4):
        for block_x in range(0, 64 // 4):
            source = donor_start + (block_y * blocks_w + block_x) * 16
            target_x = block_x + 64 // 4
            target = clean_start + (block_y * blocks_w + target_x) * 16
            output[target:target + 16] = donor[source:source + 16]
            changed_blocks.append({"source_offset": source, "target_offset": target})
    result = bytes(output)
    # The occupied Utage regions remain exact: x0..64 on both logical rows.
    for block_y in range(clean_h // 4):
        for block_x in range(64 // 4):
            offset = clean_start + (block_y * blocks_w + block_x) * 16
            if result[offset:offset + 16] != clean[offset:offset + 16]:
                raise AssertionError("occupied Utage atlas block changed")
    return result, {
        "clean_source_sha256": sha(clean),
        "official_sh_source_sha256": sha(donor),
        "output_sha256": sha(result),
        "dimensions": [clean_w, clean_h],
        "source_slot": [0, 0, 64, 32],
        "destination_slot": [64, 0, 128, 32],
        "native_bc3_blocks_copied": len(changed_blocks),
        "reencoded_blocks": 0,
        "utage_occupied_blocks_preserved": True,
    }


def node_names(raw: bytes) -> list[tuple[str, str]]:
    count = struct.unpack_from(">H", raw, 12)[0]
    cursor = raw.find(b"\0\0\0\x08SysRoot\0", 16 + count * 176)
    if cursor < 0:
        raise AssertionError("LSP name table not found")
    result = []
    for _ in range(count):
        values = []
        for _ in range(2):
            length = struct.unpack_from(">I", raw, cursor)[0]
            start = cursor + 4
            end = start + length
            values.append(raw[start:end].rstrip(b"\0").decode("ascii"))
            cursor = end
        result.append((values[0], values[1]))
    return result


def patch_layout(raw: bytes, nodes: tuple[int, ...]) -> tuple[bytes, list[dict]]:
    names = node_names(raw)
    output = bytearray(raw)
    records = []
    for index in nodes:
        name, texture = names[index]
        if name != "Kill" or not texture.endswith("cockpit_005_ID_HQ"):
            raise AssertionError({"node": index, "name": name, "texture": texture})
        offset = 16 + index * 176
        old_position = struct.unpack_from(">2f", raw, offset)
        old_geometry = struct.unpack_from(">4i", raw, offset + 0x74)
        old_uv = struct.unpack_from(">4i", raw, offset + 0x84)
        if old_position[0] >= -1.0:
            position_x = 12.0
            geometry = (-32, -16, 32, 16)
        else:
            position_x = -14.0
            geometry = (0, -16, 64, 16)
        uv = (64, 0, 128, 32)
        struct.pack_into(">f", output, offset, position_x)
        struct.pack_into(">4i", output, offset + 0x74, *geometry)
        struct.pack_into(">4i", output, offset + 0x84, *uv)
        records.append({
            "node": index,
            "name": name,
            "texture": texture,
            "position_before": list(old_position),
            "position_after": [position_x, old_position[1]],
            "geometry_before": list(old_geometry),
            "geometry_after": list(geometry),
            "uv_before": list(old_uv),
            "uv_after": list(uv),
        })
    # Every non-Kill node must remain byte-identical.
    changed_ranges = []
    for index, (left, right) in enumerate(zip(raw, output)):
        if left != right:
            changed_ranges.append(index)
    allowed = set()
    for index in nodes:
        base = 16 + index * 176
        for start, size in ((base, 4), (base + 0x74, 16), (base + 0x84, 16)):
            allowed.update(range(start, start + size))
    if not set(changed_ranges) <= allowed:
        raise AssertionError("layout changed outside Kill nodes")
    return bytes(output), records


def build_one(player: str, lsp_index: int, kill_nodes: tuple[int, ...]) -> tuple[Path, dict]:
    live_path = LIVE / "eng/id" / f"cockpit{player}.arc"
    clean_path = LIVE / "jpn/id" / f"cockpit{player}.arc"
    donor_path = SH / "eng/id" / f"cockpit{player}.arc"
    current = arc_tools.parse_arc(live_path)
    clean_arc = arc_tools.parse_arc(clean_path)
    donor_arc = arc_tools.parse_arc(donor_path)
    current_target = arc_tools.unpack(current.entries[6])
    clean_target = arc_tools.unpack(clean_arc.entries[6])
    donor_target = arc_tools.unpack(donor_arc.entries[7])
    if sha(current_target) != BROKEN_SHA:
        raise AssertionError(f"unexpected current broken payload: {player}")
    atlas, atlas_report = hybrid_atlas(clean_target, donor_target)
    old_lsp = arc_tools.unpack(current.entries[lsp_index])
    new_lsp, node_report = patch_layout(old_lsp, kill_nodes)
    rebuilt_raw = arc_tools.rebuild(current, {6: atlas, lsp_index: new_lsp})
    output = ROOT / f"cockpit{player}_v8.arc"
    output.write_bytes(rebuilt_raw)
    rebuilt = arc_tools.parse_arc(output)
    changed = []
    untouched_compressed = True
    for old, new in zip(current.entries, rebuilt.entries):
        old_raw = arc_tools.unpack(old)
        new_raw = arc_tools.unpack(new)
        if old_raw != new_raw:
            changed.append(new.index)
        elif old.compressed != new.compressed:
            untouched_compressed = False
        arc_tools.unpack(new)
    if changed != [6, lsp_index] or not untouched_compressed:
        raise AssertionError({"player": player, "changed": changed, "untouched": untouched_compressed})
    if len(atlas) != 16404 or xet_dimensions(atlas)[:2] != (128, 128):
        raise AssertionError("hybrid atlas geometry changed")
    return output, {
        "player": player,
        "source_archive": str(live_path),
        "source_archive_sha256": sha(current.data),
        "output_archive": str(output),
        "output_archive_sha256": sha(rebuilt_raw),
        "entry_count": len(rebuilt.entries),
        "changed_resource_indices": changed,
        "texture_entry": 6,
        "layout_entry": lsp_index,
        "atlas": atlas_report,
        "kill_nodes": node_report,
        "all_other_compressed_blobs_identical": True,
    }


def package(outputs: dict[str, Path], validation: dict) -> dict:
    if sha_file(BASE_ZIP) != BASE_ZIP_SHA:
        raise AssertionError("V7 base ZIP changed")
    if RELEASE_DIR.exists():
        if RELEASE_DIR.parent != ROOT or RELEASE_DIR.name != RELEASE:
            raise AssertionError(RELEASE_DIR)
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)
    with zipfile.ZipFile(BASE_ZIP) as source:
        if source.testzip() is not None:
            raise AssertionError("V7 CRC failure")
        base_names = source.namelist()
        source.extractall(RELEASE_DIR)
    (RELEASE_DIR / REL1).parent.mkdir(parents=True, exist_ok=True)
    (RELEASE_DIR / REL2).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(outputs["1P"], RELEASE_DIR / REL1)
    shutil.copy2(outputs["2P"], RELEASE_DIR / REL2)
    manifest = {
        "patch": "Utage Cockpit KOs Repair V8 cumulative over V7",
        "created": "2026-08-30",
        "base_zip_sha256": BASE_ZIP_SHA,
        "official_donor": "Samurai Heroes cockpit_005_ID_HQ native BC3 KOs slot",
        "official_donor_raw_sha256": DONOR_SHA,
        "targets": [REL1.as_posix(), REL2.as_posix()],
        "method": (
            "Restore the clean Utage 128x128 atlas, copy the official SH KOs slot as native BC3 blocks "
            "into an unused atlas slot, and reroute only Kill nodes in the 1P/2P layouts."
        ),
        "preserved": "Utage-only Nyusin/Ninnuki labels, all non-Kill layout nodes, archive topology, and V7 content.",
        "validation": validation,
        "engine_smoke_test": "required",
    }
    (RELEASE_DIR / "COCKPIT_KOS_V8_MANIFEST_2026-08-30.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (RELEASE_DIR / "COCKPIT_KOS_V8_VALIDATION_2026-08-30.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    readme = """Sengoku BASARA 3 Utage English Patch - Cockpit KOs Repair V8

This package is cumulative over V7. Merge PS3_GAME into the extracted game root and overwrite.

V8 repairs cockpit_005_ID_HQ in both cockpit1P.arc and cockpit2P.arc. The previous English payload had overwritten Utage's occupied 128x128 atlas area and produced the corrupted Japanese overlap shown in the supplied screenshot.

The repair starts from the clean Utage atlas, copies Samurai Heroes' official KOs cell as native BC3 blocks into an unused slot with no recompression, and redirects only the Kill/KOs layout nodes to that slot. Utage-only counter labels remain intact. No whole SH cockpit archive or LSP was transplanted.

Offline ARC, resource, byte-scope, ZIP, and checksum validation pass. Cold-boot gameplay testing is still required for both 1P and 2P HUDs.
"""
    (RELEASE_DIR / "README_COCKPIT_KOS_V8.txt").write_text(readme, encoding="utf-8")
    test = """Sengoku BASARA 3 Utage English Patch - V8 TEST FIRST

1. Fully close RPCS3.
2. Merge PS3_GAME into the extracted Utage game root and overwrite.
3. Cold boot into a 1P battle and confirm the HUD reads KOs cleanly.
4. If available, test 2P and confirm the same KOs graphic.
5. Check nearby Utage-only counters for missing or corrupted labels.
6. Regression-check Quick Battles, Retry, and Nobunaga's faction label.

Send a gameplay screenshot of the KOs counter if alignment needs one final adjustment.
"""
    (RELEASE_DIR / "README_TEST_FIRST.txt").write_text(test, encoding="utf-8")
    files = sorted(path for path in RELEASE_DIR.rglob("*") if path.is_file())
    expected = len(base_names) + 5
    if len(files) != expected:
        raise AssertionError({"files": len(files), "expected": expected})
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, path.relative_to(RELEASE_DIR).as_posix())
    with zipfile.ZipFile(OUTPUT_ZIP) as output:
        if output.testzip() is not None or len(output.namelist()) != expected:
            raise AssertionError("V8 ZIP integrity failure")
    zip_sha = sha_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_sha}  {OUTPUT_ZIP.name}\n", encoding="ascii")
    shutil.copy2(OUTPUT_ZIP, DOWNLOAD_ZIP)
    shutil.copy2(OUTPUT_SHA, DOWNLOAD_SHA)
    return {"zip": str(DOWNLOAD_ZIP), "zip_sha256": zip_sha, "zip_file_count": expected}


def independent_verify(package_report: dict, validation: dict) -> dict:
    with zipfile.ZipFile(BASE_ZIP) as base_zip, zipfile.ZipFile(OUTPUT_ZIP) as v8_zip:
        if base_zip.testzip() is not None or v8_zip.testzip() is not None:
            raise AssertionError("CRC failure")
        base_names = set(base_zip.namelist())
        v8_names = set(v8_zip.namelist())
        added = sorted(v8_names - base_names)
        removed = sorted(base_names - v8_names)
        changed = sorted(name for name in base_names & v8_names if base_zip.read(name) != v8_zip.read(name))
        expected_added = sorted([
            REL1.as_posix(), REL2.as_posix(),
            "COCKPIT_KOS_V8_MANIFEST_2026-08-30.json",
            "COCKPIT_KOS_V8_VALIDATION_2026-08-30.json",
            "README_COCKPIT_KOS_V8.txt",
        ])
        if added != expected_added or removed or changed != ["README_TEST_FIRST.txt"]:
            raise AssertionError({"added": added, "removed": removed, "changed": changed})
        with tempfile.TemporaryDirectory(prefix="utage_v8_verify_") as temp:
            root = Path(temp)
            v8_zip.extractall(root)
            arcs = sorted(root.rglob("*.arc"))
            entries = resources = 0
            warnings = []
            for path in arcs:
                archive = arc_tools.parse_arc(path)
                entries += len(archive.entries)
                for entry in archive.entries:
                    raw = arc_tools.unpack(entry)
                    resources += 1
                    if len(raw) != entry.raw_size:
                        warnings.append({"archive": path.relative_to(root).as_posix(), "entry": entry.index, "declared": entry.raw_size, "actual": len(raw)})
            if (len(arcs), entries, resources) != (37, 630, 630):
                raise AssertionError((len(arcs), entries, resources))
    report = {
        "status": "pass",
        "zip_sha256": package_report["zip_sha256"],
        "zip_file_count": len(v8_names),
        "added_members": added,
        "changed_base_members": changed,
        "removed_members": removed,
        "arc_file_count": len(arcs),
        "arc_entry_count": entries,
        "resource_unpack_count": resources,
        "cockpit_validation": validation,
        "declared_size_warnings": warnings,
        "runtime_test": "required",
    }
    (ROOT / "V8_INDEPENDENT_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    one, one_report = build_one("1P", 18, (34, 96))
    two, two_report = build_one("2P", 19, (34, 81, 98))
    validation = {"status": "pass", "archives": [one_report, two_report]}
    (ROOT / "V8_COCKPIT_VALIDATION.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    package_report = package({"1P": one, "2P": two}, validation)
    independent = independent_verify(package_report, validation)
    (ROOT / "V8_PACKAGE_VALIDATION.json").write_text(json.dumps(package_report, indent=2), encoding="utf-8")
    print(json.dumps({"package": package_report, "independent": independent}, indent=2))


if __name__ == "__main__":
    main()
