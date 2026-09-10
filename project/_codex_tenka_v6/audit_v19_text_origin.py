#!/usr/bin/env python3
"""Independent post-install audit for V19 battle-dialogue text origin."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path


WORK = Path(__file__).resolve().parent
UTAGE = Path(r"E:\Utage Patching New")
SH = Path(r"E:\SAMURAI HEROES")
sys.path.insert(0, str(WORK))

import arc_tools as A  # noqa: E402
import build_v18_dialogue_alignment as V18  # noqa: E402


LSP = 0x60DD1B16
RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
V18_DIR = WORK / "Utage_Battle_Dialogue_V18_VERTICAL_ALIGNMENT_ROOT_READY"
V19_DIR = WORK / "Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY"
V19_ZIP = WORK / "Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY.zip"
V19_SHA = WORK / "Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY.zip.sha256"
V19_REPORT = WORK / "V19_TEXT_ORIGIN_VALIDATION.json"
DONOR = SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


def lsp(arc: A.Archive, name: str) -> tuple[A.Entry, bytes]:
    hits = [entry for entry in arc.entries if entry.type_hash == LSP and entry.name == name]
    if len(hits) != 1:
        raise AssertionError({"name": name, "matches": len(hits)})
    return hits[0], A.unpack(hits[0])


def first_special(raw: bytes) -> tuple[int, bytes]:
    _, _, starts = V18.animation_area(raw)
    for ordinal, (lo, hi) in enumerate(zip(starts, starts[1:])):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == 0xFFFFFFFF:
            if ordinal != 0 or len(block) != 208:
                raise AssertionError({"ordinal": ordinal, "length": len(block)})
            return lo, block
    raise AssertionError("special-root block absent")


def main() -> None:
    live_hashes = []
    jobs = []
    donor_arc = A.parse_arc(DONOR)
    _, donor_lsp = lsp(donor_arc, r"id\lsp\abr\cockpit\cockpit")
    _, donor_block = first_special(donor_lsp)

    for relative in RELATIVES:
        base_path = V18_DIR / relative
        release_path = V19_DIR / relative
        live_path = UTAGE / relative
        if not base_path.is_file() or not release_path.is_file() or not live_path.is_file():
            raise FileNotFoundError(relative)
        release_raw = release_path.read_bytes()
        live_raw = live_path.read_bytes()
        if release_raw != live_raw:
            raise AssertionError(f"live/release mismatch: {relative}")

        base_arc = A.parse_arc(base_path)
        live_arc = A.parse_arc(live_path)
        if len(base_arc.entries) != 39 or len(live_arc.entries) != 39:
            raise AssertionError("unexpected cockpit1P entry count")
        base_entry, base_lsp = lsp(base_arc, r"id\lsp\jpn\cockpit\cockpit")
        live_entry, live_lsp = lsp(live_arc, r"id\lsp\jpn\cockpit\cockpit")
        if base_entry.index != 18 or live_entry.index != 18:
            raise AssertionError("dialogue LSP is not ARC entry 18")

        changed_entries = []
        preserved_compressed = True
        for before, after in zip(base_arc.entries, live_arc.entries):
            if before.name != after.name or before.type_hash != after.type_hash:
                raise AssertionError("ARC entry identity drift")
            before_raw = A.unpack(before)
            after_raw = A.unpack(after)
            if before_raw != after_raw:
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
        base_lo, base_block = first_special(base_lsp)
        live_lo, live_block = first_special(live_lsp)
        if base_lo != live_lo or raw_changes != [base_lo + 3, base_lo + 107]:
            raise AssertionError(
                {"base_special_offset": base_lo, "live_special_offset": live_lo, "raw_changes": raw_changes}
            )
        if live_block != donor_block:
            raise AssertionError("installed 1P special-root block is not exact SH")
        values_before = [struct.unpack_from(">I", base_block, offset)[0] for offset in (0, 104)]
        values_after = [struct.unpack_from(">I", live_block, offset)[0] for offset in (0, 104)]
        if values_before != [0, 0] or values_after != [1, 1]:
            raise AssertionError({"values_before": values_before, "values_after": values_after})

        for entry in live_arc.entries:
            A.unpack(entry)
        live_hashes.append(sha(live_raw))
        jobs.append(
            {
                "relative": relative.as_posix(),
                "v18_arc_sha256": sha_file(base_path),
                "v19_arc_sha256": sha(live_raw),
                "entry_count": len(live_arc.entries),
                "changed_entries_vs_v18": changed_entries,
                "lsp_length": len(live_lsp),
                "lsp_sha256": sha(live_lsp),
                "raw_lsp_changes_vs_v18": raw_changes,
                "special_root_values_before": values_before,
                "special_root_values_after": values_after,
                "special_root_exact_sh": True,
                "untouched_compressed_resources_preserved": True,
            }
        )

    if len(set(live_hashes)) != 1:
        raise AssertionError("live ENG/JPN archives are not mirrored")

    expected_members = {
        relative.as_posix() for relative in RELATIVES
    } | {"README_V19.txt", "VALIDATION_V19.json"}
    with zipfile.ZipFile(V19_ZIP) as package:
        if package.testzip() is not None:
            raise AssertionError("V19 ZIP CRC failure")
        members = {item.filename for item in package.infolist()}
        if members != expected_members:
            raise AssertionError({"package_members": sorted(members)})
        for relative in RELATIVES:
            if package.read(relative.as_posix()) != (UTAGE / relative).read_bytes():
                raise AssertionError(f"packaged/live mismatch: {relative}")

    zip_hash = sha_file(V19_ZIP)
    sidecar = V19_SHA.read_text(encoding="ascii").strip().split()[0]
    if sidecar != zip_hash:
        raise AssertionError({"sidecar": sidecar, "actual": zip_hash})
    report = json.loads(V19_REPORT.read_text(encoding="utf-8"))
    if report.get("status") != "pass" or report.get("offline_validation") != "pass":
        raise AssertionError("V19 validation report is not pass")
    if report["two_player_corroboration"]["enable_values"] != [1, 0]:
        raise AssertionError("V19 report has incorrect 2P corroboration")

    print(
        json.dumps(
            {
                "status": "pass",
                "jobs": jobs,
                "mirrored_live_arc_sha256": live_hashes[0],
                "cockpit2p_sha256_unchanged": sha_file(
                    UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc"
                ),
                "package_members": sorted(expected_members),
                "package_zip_sha256": zip_hash,
                "zip_crc": "pass",
                "sidecar_matches": True,
                "runtime_test": "required",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
