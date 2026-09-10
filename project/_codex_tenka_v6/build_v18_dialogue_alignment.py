#!/usr/bin/env python3
"""V18 - repair the in-battle dialogue window's vertical animation alignment.

V16 correctly ported Samurai Heroes' Western message-window node geometry, but
left Utage's two animated Y values on the ``3_0`` dialogue root.  The resulting
mixed state uses SH's base node position (Y = 8) and Utage's animated position
(Y = -2), so the panel and its text anchor do not line up at runtime.

V17 must not be used as a base: its ordinal name-to-block mapping was wrong.
The LSP name table contains entries without a matching boundary block, so the
range called ``Ani 0_0_2`` actually targeted unrelated Meter/Basara/partner HUD
nodes.  This builder starts from the byte-exact pre-V17 backup (the installed
V16 state), identifies animation blocks by stable node ID, and changes only the
four 32-bit Y key values on node ``3_0`` from -2.0 to SH's 3.0.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path


WORK = Path(__file__).resolve().parent
UTAGE = Path(r"E:\Utage Patching New")
SH = Path(r"E:\SAMURAI HEROES")
sys.path.insert(0, str(WORK))

import arc_tools as A  # noqa: E402


LSP = 0x60DD1B16
NODE0 = 16
NODE_SIZE = 176
BOUNDARY = re.compile(rb"\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00")

BACKUP_V16 = WORK / "V17_BACKUP_cockpit1P_pre_v17.zip"
BACKUP_PRE_V18 = WORK / "V18_BACKUP_cockpit1P_pre_v18.zip"
BASE_DIR = WORK / "V18_BASE_FROM_PRE_V17_BACKUP"
RELEASE_NAME = "Utage_Battle_Dialogue_V18_VERTICAL_ALIGNMENT_ROOT_READY"
RELEASE_DIR = WORK / RELEASE_NAME
OUTPUT_ZIP = WORK / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = WORK / f"{RELEASE_NAME}.zip.sha256"
REPORT = WORK / "V18_DIALOGUE_ALIGNMENT_VALIDATION.json"

RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
DONOR = SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"
DONOR_LSP_NAME = r"id\lsp\abr\cockpit\cockpit"
UTAGE_LSP_NAME = r"id\lsp\jpn\cockpit\cockpit"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_build_dir(path: Path) -> None:
    if path.parent != WORK or not path.name.startswith(("V18_", RELEASE_NAME)):
        raise AssertionError(f"unsafe build directory: {path}")
    if path.exists():
        shutil.rmtree(path)


def lsp_entry(archive: A.Archive, name: str) -> A.Entry:
    hits = [entry for entry in archive.entries if entry.type_hash == LSP and entry.name == name]
    if len(hits) != 1:
        raise AssertionError(f"{name}: expected one LSP entry, found {len(hits)}")
    return hits[0]


def node_names(raw: bytes) -> tuple[int, list[str]]:
    count = struct.unpack_from(">H", raw, 12)[0]
    marker = b"\x00\x00\x00\x08SysRoot\x00"
    cursor = raw.find(marker, NODE0 + count * NODE_SIZE)
    if cursor < 0:
        raise AssertionError("LSP node-name table not found")
    names: list[str] = []
    for index in range(count * 2):
        length = struct.unpack_from(">I", raw, cursor)[0]
        if length < 1 or cursor + 4 + length > len(raw):
            raise AssertionError(f"invalid LSP string {index} at 0x{cursor:X}")
        if index % 2 == 0:
            names.append(raw[cursor + 4:cursor + 3 + length].decode("latin-1"))
        cursor += 4 + length
    return count, names


def animation_area(raw: bytes) -> tuple[int, int, list[int]]:
    count = struct.unpack_from(">H", raw, 12)[0]
    start = NODE0 + count * NODE_SIZE
    table = raw.find(b"\x00\x00\x00\x08SysRoot\x00", start)
    if table < 0:
        raise AssertionError("LSP name table not found")
    starts = [match.start() - 4 for match in BOUNDARY.finditer(raw, start, table)]
    starts.append(table)
    return start, table, starts


def stable_node_id(raw: bytes, wanted_name: str) -> tuple[int, int]:
    _, names = node_names(raw)
    hits = [index for index, name in enumerate(names) if name == wanted_name]
    if len(hits) != 1:
        raise AssertionError(f"node {wanted_name!r}: found {len(hits)}")
    index = hits[0]
    node_id = struct.unpack_from(">I", raw, NODE0 + index * NODE_SIZE + 0x50)[0]
    return index, node_id


def blocks_for_node(raw: bytes, node_id: int) -> list[tuple[int, int, bytes]]:
    _, _, starts = animation_area(raw)
    matches: list[tuple[int, int, bytes]] = []
    for index, (lo, hi) in enumerate(zip(starts, starts[1:])):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == node_id:
            matches.append((lo, hi, block))
    return matches


def verify_exact_blocks(base: bytes, donor: bytes, name: str, expected_count: int) -> dict:
    base_index, base_id = stable_node_id(base, name)
    donor_index, donor_id = stable_node_id(donor, name)
    if base_id != donor_id:
        raise AssertionError(f"{name}: stable ID differs: {base_id} != {donor_id}")
    base_blocks = blocks_for_node(base, base_id)
    donor_blocks = blocks_for_node(donor, donor_id)
    if len(base_blocks) != expected_count or len(donor_blocks) != expected_count:
        raise AssertionError(
            f"{name}: expected {expected_count} blocks, found "
            f"{len(base_blocks)} / {len(donor_blocks)}"
        )
    if [block for _, _, block in base_blocks] != [block for _, _, block in donor_blocks]:
        raise AssertionError(f"{name}: supposedly shared blocks differ")
    return {
        "node": name,
        "stable_id": base_id,
        "utage_node_index": base_index,
        "sh_node_index": donor_index,
        "block_count": expected_count,
        "block_sha256": [sha(block) for _, _, block in base_blocks],
    }


def patch_dialogue_root(base: bytes, donor: bytes) -> tuple[bytes, dict]:
    base_index, base_id = stable_node_id(base, "3_0")
    donor_index, donor_id = stable_node_id(donor, "3_0")
    if base_id != donor_id or base_id != 72:
        raise AssertionError(f"unexpected 3_0 stable IDs: {base_id}, {donor_id}")
    base_blocks = blocks_for_node(base, base_id)
    donor_blocks = blocks_for_node(donor, donor_id)
    if len(base_blocks) != 2 or len(donor_blocks) != 2:
        raise AssertionError(f"3_0 block counts: {len(base_blocks)}, {len(donor_blocks)}")

    output = bytearray(base)
    edits = []
    for block_index, ((base_lo, base_hi, before), (_, _, after)) in enumerate(
        zip(base_blocks, donor_blocks)
    ):
        if len(before) != 280 or len(after) != 280:
            raise AssertionError(f"3_0 block {block_index}: unexpected lengths")
        differing = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
        if differing != [136, 137, 160, 161]:
            raise AssertionError(f"3_0 block {block_index}: unexpected differences {differing}")
        for relative_offset in (136, 160):
            old_value = struct.unpack_from(">f", before, relative_offset)[0]
            new_value = struct.unpack_from(">f", after, relative_offset)[0]
            if old_value != -2.0 or new_value != 3.0:
                raise AssertionError(
                    f"3_0 block {block_index} +0x{relative_offset:X}: "
                    f"{old_value} -> {new_value}"
                )
            absolute = base_lo + relative_offset
            output[absolute:absolute + 4] = after[relative_offset:relative_offset + 4]
            edits.append(
                {
                    "block": block_index,
                    "lsp_offset": absolute,
                    "block_offset": relative_offset,
                    "before_f32": old_value,
                    "after_f32": new_value,
                }
            )
        if bytes(output[base_lo:base_hi]) != after:
            raise AssertionError(f"3_0 block {block_index} did not become exact SH")

    changed = [index for index, pair in enumerate(zip(base, output)) if pair[0] != pair[1]]
    expected_changed = sorted(
        edit["lsp_offset"] + delta
        for edit in edits
        for delta in range(4)
        if base[edit["lsp_offset"] + delta] != output[edit["lsp_offset"] + delta]
    )
    if changed != expected_changed or len(changed) != 8:
        raise AssertionError({"changed": changed, "expected": expected_changed})

    return bytes(output), {
        "target_node": "3_0",
        "stable_id": base_id,
        "utage_node_index": base_index,
        "sh_node_index": donor_index,
        "blocks_changed": 2,
        "f32_values_changed": 4,
        "raw_bytes_changed": len(changed),
        "changed_raw_byte_offsets": changed,
        "edits": edits,
    }


def create_backup(paths: list[Path]) -> None:
    if BACKUP_PRE_V18.exists():
        return
    with zipfile.ZipFile(BACKUP_PRE_V18, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in paths:
            output.write(path, path.relative_to(UTAGE).as_posix())
    with zipfile.ZipFile(BACKUP_PRE_V18) as check:
        if check.testzip() is not None or len(check.infolist()) != len(paths):
            raise AssertionError("pre-V18 backup verification failed")


def main() -> None:
    if not BACKUP_V16.is_file():
        raise FileNotFoundError(BACKUP_V16)
    live_paths = [UTAGE / relative for relative in RELATIVES]
    if not all(path.is_file() for path in live_paths):
        raise FileNotFoundError("live cockpit1P pair is incomplete")
    live_hashes_before = {str(path): sha_file(path) for path in live_paths}
    if len(set(live_hashes_before.values())) != 1:
        raise AssertionError("live ENG/JPN cockpit1P archives are not mirrored")
    create_backup(live_paths)

    remove_build_dir(BASE_DIR)
    remove_build_dir(RELEASE_DIR)
    BASE_DIR.mkdir(parents=True)
    RELEASE_DIR.mkdir(parents=True)
    with zipfile.ZipFile(BACKUP_V16) as source:
        if source.testzip() is not None:
            raise AssertionError("pre-V17 backup ZIP CRC failure")
        source.extractall(BASE_DIR)

    donor_arc = A.parse_arc(DONOR)
    donor_lsp = A.unpack(lsp_entry(donor_arc, DONOR_LSP_NAME))
    job_reports = []
    outputs = []
    for relative in RELATIVES:
        base_path = BASE_DIR / relative
        base_arc = A.parse_arc(base_path)
        base_entry = lsp_entry(base_arc, UTAGE_LSP_NAME)
        base_lsp = A.unpack(base_entry)

        shared_blocks = [
            verify_exact_blocks(base_lsp, donor_lsp, "Mess1", 3),
            verify_exact_blocks(base_lsp, donor_lsp, "Line_U", 3),
            verify_exact_blocks(base_lsp, donor_lsp, "3_1", 2),
        ]
        patched_lsp, edit_report = patch_dialogue_root(base_lsp, donor_lsp)
        rebuilt_raw = A.rebuild(base_arc, {base_entry.index: patched_lsp})

        output_path = RELEASE_DIR / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(rebuilt_raw)
        output_arc = A.parse_arc(output_path)
        if len(output_arc.entries) != len(base_arc.entries):
            raise AssertionError("ARC entry count changed")
        changed_entries = []
        untouched_compressed_preserved = True
        for old, new in zip(base_arc.entries, output_arc.entries):
            if A.unpack(old) != A.unpack(new):
                changed_entries.append(new.index)
            elif old.compressed != new.compressed:
                untouched_compressed_preserved = False
        if changed_entries != [base_entry.index] or not untouched_compressed_preserved:
            raise AssertionError(
                {
                    "changed_entries": changed_entries,
                    "untouched_compressed_preserved": untouched_compressed_preserved,
                }
            )
        rebuilt_lsp = A.unpack(output_arc.entries[base_entry.index])
        if rebuilt_lsp != patched_lsp:
            raise AssertionError("patched LSP did not survive ARC rebuild")
        for entry in output_arc.entries:
            A.unpack(entry)

        outputs.append(output_path)
        job_reports.append(
            {
                "relative": relative.as_posix(),
                "base": str(base_path),
                "base_arc_sha256": sha(base_arc.data),
                "base_lsp_sha256": sha(base_lsp),
                "output": str(output_path),
                "output_arc_sha256": sha(rebuilt_raw),
                "output_lsp_sha256": sha(patched_lsp),
                "entry_count": len(output_arc.entries),
                "changed_arc_entries": changed_entries,
                "untouched_compressed_resources_preserved": True,
                "shared_sh_animation_proofs": shared_blocks,
                "vertical_alignment_edit": edit_report,
            }
        )

    output_hashes = {sha_file(path) for path in outputs}
    if len(output_hashes) != 1:
        raise AssertionError("V18 ENG/JPN outputs are not byte-identical")

    report = {
        "status": "pass",
        "patch": "Utage Battle Dialogue V18 Vertical Alignment",
        "diagnosis": (
            "V16 installed SH's dialogue-panel node geometry but retained Utage's "
            "animated 3_0 Y keys. V17 used an invalid ordinal animation-name mapping "
            "and spliced unrelated HUD blocks; V18 starts from the pre-V17 V16 backup, "
            "proves the long-window, text-line, and text-container blocks already equal "
            "SH, and changes only four 3_0 Y values from -2.0 to 3.0."
        ),
        "pre_v17_backup": str(BACKUP_V16),
        "pre_v17_backup_sha256": sha_file(BACKUP_V16),
        "pre_v18_runtime_backup": str(BACKUP_PRE_V18),
        "pre_v18_runtime_backup_sha256": sha_file(BACKUP_PRE_V18),
        "live_hashes_before": live_hashes_before,
        "donor": str(DONOR),
        "donor_sha256": sha_file(DONOR),
        "jobs": job_reports,
        "mirrored_output_sha256": next(iter(output_hashes)),
        "offline_validation": "pass",
        "runtime_test": "required",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RELEASE_DIR / "VALIDATION_V18.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (RELEASE_DIR / "README_V18.txt").write_text(
        """Sengoku BASARA 3 Utage - Battle Dialogue V18 Vertical Alignment

V18 corrects the vertical orientation of the in-battle character dialogue
window while preserving the repaired V15 message/font system and the cumulative
Utage cockpit HUD.

Diagnosis: V16 installed Samurai Heroes' Western panel geometry, but its two
dialogue-root animation blocks still used Utage's Y=-2 keys. V17 then selected
animation data by a drifting ordinal name map and replaced unrelated HUD tracks.
V18 starts from the clean pre-V17 V16 backup and changes only four 32-bit Y
values on stable node 3_0 from -2.0 to Samurai Heroes' 3.0. The three long-box
Mess1 tracks, three Line_U tracks, and two 3_1 text-container tracks are proven
byte-identical to official Samurai Heroes and are left untouched.

Merge PS3_GAME into the Utage game root and overwrite. Fully close RPCS3 first,
then cold boot m034/pl015 without a save state. Confirm the Katakura line shown
in the reference screenshot is vertically centered, then trigger a three-line
line to verify the expanded panel, name plate, portrait, health/Basara meters,
partner HUD, KOs counter, and mission banner.
""",
        encoding="utf-8",
    )

    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    files = sorted(path for path in RELEASE_DIR.rglob("*") if path.is_file())
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, path.relative_to(RELEASE_DIR).as_posix())
    with zipfile.ZipFile(OUTPUT_ZIP) as check:
        if check.testzip() is not None or len(check.infolist()) != len(files):
            raise AssertionError("V18 package ZIP verification failed")
    zip_hash = sha_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_hash}  {OUTPUT_ZIP.name}\n", encoding="ascii")

    # Install the validated, mirrored outputs into the live game root.
    for relative, output_path in zip(RELATIVES, outputs):
        shutil.copy2(output_path, UTAGE / relative)
    live_hashes_after = {str(path): sha_file(path) for path in live_paths}
    if set(live_hashes_after.values()) != output_hashes:
        raise AssertionError("live V18 install hash mismatch")

    print(
        json.dumps(
            {
                "status": "pass",
                "report": str(REPORT),
                "release_dir": str(RELEASE_DIR),
                "zip": str(OUTPUT_ZIP),
                "zip_sha256": zip_hash,
                "zip_files": len(files),
                "mirrored_cockpit1p_sha256": next(iter(output_hashes)),
                "live_hashes_after": live_hashes_after,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
