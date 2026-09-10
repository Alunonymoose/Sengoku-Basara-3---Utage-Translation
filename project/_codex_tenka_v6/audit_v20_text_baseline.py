#!/usr/bin/env python3
"""Independent post-install audit for V20 text-baseline compensation."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path


WORK = Path(__file__).resolve().parent
UTAGE = Path(r"E:\Utage Patching New")
sys.path.insert(0, str(WORK))

import arc_tools as A  # noqa: E402
import build_v18_dialogue_alignment as V18  # noqa: E402


LSP = 0x60DD1B16
RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
BASE_DIR = WORK / "Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY"
RELEASE_DIR = WORK / "Utage_Battle_Dialogue_V20_TEXT_BASELINE_COMPENSATION_ROOT_READY"
PACKAGE = WORK / "Utage_Battle_Dialogue_V20_TEXT_BASELINE_COMPENSATION_ROOT_READY.zip"
SIDECAR = WORK / "Utage_Battle_Dialogue_V20_TEXT_BASELINE_COMPENSATION_ROOT_READY.zip.sha256"
REPORT = WORK / "V20_TEXT_BASELINE_VALIDATION.json"
EXPECTED_RAW_CHANGES = [20437, 20613, 22724, 45188, 45189, 45212, 45213, 45468, 45469, 45492, 45493]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def lsp(arc: A.Archive) -> tuple[A.Entry, bytes]:
    hits = [
        entry
        for entry in arc.entries
        if entry.type_hash == LSP and entry.name == r"id\lsp\jpn\cockpit\cockpit"
    ]
    if len(hits) != 1:
        raise AssertionError({"LSP matches": len(hits)})
    return hits[0], A.unpack(hits[0])


def node_y(raw: bytes, index: int) -> float:
    return struct.unpack_from(">f", raw, V18.NODE0 + index * V18.NODE_SIZE + 4)[0]


def main() -> None:
    jobs = []
    live_hashes = []
    for relative in RELATIVES:
        base_path = BASE_DIR / relative
        release_path = RELEASE_DIR / relative
        live_path = UTAGE / relative
        if release_path.read_bytes() != live_path.read_bytes():
            raise AssertionError(f"release/live mismatch: {relative}")
        base_arc = A.parse_arc(base_path)
        live_arc = A.parse_arc(live_path)
        if len(base_arc.entries) != 39 or len(live_arc.entries) != 39:
            raise AssertionError("unexpected entry count")
        base_entry, base_lsp = lsp(base_arc)
        live_entry, live_lsp = lsp(live_arc)
        if base_entry.index != 18 or live_entry.index != 18 or len(live_lsp) != 91480:
            raise AssertionError("unexpected dialogue LSP identity/size")

        changed_entries = []
        preserved_compressed = True
        for before, after in zip(base_arc.entries, live_arc.entries):
            if before.name != after.name or before.type_hash != after.type_hash:
                raise AssertionError("entry identity drift")
            if A.unpack(before) != A.unpack(after):
                changed_entries.append(after.index)
            elif before.compressed != after.compressed:
                preserved_compressed = False
        if changed_entries != [18] or not preserved_compressed:
            raise AssertionError(
                {"changed_entries": changed_entries, "preserved_compressed": preserved_compressed}
            )
        raw_changes = [
            index for index, pair in enumerate(zip(base_lsp, live_lsp)) if pair[0] != pair[1]
        ]
        if raw_changes != EXPECTED_RAW_CHANGES:
            raise AssertionError({"raw_changes": raw_changes, "expected": EXPECTED_RAW_CHANGES})

        before_y = [node_y(base_lsp, index) for index in (116, 117, 129)]
        after_y = [node_y(live_lsp, index) for index in (116, 117, 129)]
        if before_y != [330.0, 8.0, 0.0] or after_y != [322.0, 16.0, 8.0]:
            raise AssertionError({"before_y": before_y, "after_y": after_y})
        before_blocks = V18.blocks_for_node(base_lsp, 72)
        after_blocks = V18.blocks_for_node(live_lsp, 72)
        before_keys = [
            struct.unpack_from(">f", block, offset)[0]
            for _, _, block in before_blocks
            for offset in (0x88, 0xA0)
        ]
        after_keys = [
            struct.unpack_from(">f", block, offset)[0]
            for _, _, block in after_blocks
            for offset in (0x88, 0xA0)
        ]
        if before_keys != [3.0] * 4 or after_keys != [11.0] * 4:
            raise AssertionError({"before_keys": before_keys, "after_keys": after_keys})
        world_before = [before_y[0] + before_y[1], before_y[0] + 3.0, before_y[0] + before_y[2]]
        world_after = [after_y[0] + after_y[1], after_y[0] + 11.0, after_y[0] + after_y[2]]
        if world_before != world_after or world_after != [338.0, 333.0, 330.0]:
            raise AssertionError({"world_before": world_before, "world_after": world_after})

        _, _, starts = V18.animation_area(live_lsp)
        first = live_lsp[starts[0]:starts[1]]
        special_values = [struct.unpack_from(">I", first, offset)[0] for offset in (0, 104)]
        if len(first) != 208 or special_values != [1, 1]:
            raise AssertionError({"special_length": len(first), "special_values": special_values})
        for entry in live_arc.entries:
            A.unpack(entry)

        live_hash = sha(live_path.read_bytes())
        live_hashes.append(live_hash)
        jobs.append(
            {
                "relative": relative.as_posix(),
                "v19_arc_sha256": sha(base_path.read_bytes()),
                "v20_arc_sha256": live_hash,
                "changed_entries_vs_v19": changed_entries,
                "raw_lsp_changes_vs_v19": raw_changes,
                "node_y_before": before_y,
                "node_y_after": after_y,
                "panel_world_y_before": world_before,
                "panel_world_y_after": world_after,
                "text_anchor_before": before_y[0],
                "text_anchor_after": after_y[0],
                "v19_special_root_preserved": special_values,
                "untouched_compressed_resources_preserved": True,
            }
        )
    if len(set(live_hashes)) != 1:
        raise AssertionError("ENG/JPN live outputs are not mirrored")

    expected_members = {relative.as_posix() for relative in RELATIVES} | {
        "README_V20.txt",
        "VALIDATION_V20.json",
    }
    with zipfile.ZipFile(PACKAGE) as archive:
        if archive.testzip() is not None:
            raise AssertionError("ZIP CRC failure")
        members = {item.filename for item in archive.infolist()}
        if members != expected_members:
            raise AssertionError({"members": sorted(members)})
        for relative in RELATIVES:
            if archive.read(relative.as_posix()) != (UTAGE / relative).read_bytes():
                raise AssertionError(f"package/live mismatch: {relative}")
    zip_hash = sha(PACKAGE.read_bytes())
    if SIDECAR.read_text(encoding="ascii").split()[0] != zip_hash:
        raise AssertionError("SHA sidecar mismatch")
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report.get("status") != "pass" or report.get("offline_validation") != "pass":
        raise AssertionError("validation report not pass")

    print(
        json.dumps(
            {
                "status": "pass",
                "jobs": jobs,
                "mirrored_live_arc_sha256": live_hashes[0],
                "cockpit2p_sha256_unchanged": sha(
                    (UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc").read_bytes()
                ),
                "package_members": sorted(expected_members),
                "package_zip_sha256": zip_hash,
                "zip_crc": "pass",
                "runtime_test": "required",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
