#!/usr/bin/env python3
"""V19 - enable the SH special-root tracks that anchor 1P battle text.

V18 already makes the 1P dialogue panel geometry and all relevant animation
blocks byte-exact to Samurai Heroes.  The SH FIM and ASCII font are also used
verbatim.  Runtime comparison nevertheless shows the glyph block about 12-14
output pixels low while the panel, portrait, and name plate are correct.

The only remaining difference in the first shared 1P animation block is two
disabled records targeting special node ID 0xFFFFFFFF.  Official SH enables
both records, and Utage's own 2P layout already agrees with SH.  V19 changes
only those two big-endian u32 enable values from 0 to 1.  No node coordinate,
texture, FIM, font, message, or 2P resource is changed.
"""

from __future__ import annotations

import hashlib
import json
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
import build_v18_dialogue_alignment as V18  # noqa: E402


LSP = 0x60DD1B16
EXPECTED_V18_ARC_SHA256 = "888078d0cfc7fdba2033c0feb17a552a3a1f450d5de529fafbbc51b47878edd6"
EXPECTED_V18_LSP_SHA256 = "f0507ca166065c3d0cfcbdc0030454d7282f76937baa77877df1eea063555a3f"

RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
DONOR_1P = SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"
DONOR_2P = SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc"
UTAGE_2P = UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc"

UTAGE_LSP_1P = r"id\lsp\jpn\cockpit\cockpit"
DONOR_LSP_1P = r"id\lsp\abr\cockpit\cockpit"
UTAGE_LSP_2P = r"id\lsp\jpn\cockpit\2p"
DONOR_LSP_2P = r"id\lsp\abr\cockpit\2p"

BACKUP = WORK / "V19_BACKUP_cockpit1P_pre_v19.zip"
RELEASE_NAME = "Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY"
RELEASE_DIR = WORK / RELEASE_NAME
OUTPUT_ZIP = WORK / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = WORK / f"{RELEASE_NAME}.zip.sha256"
REPORT = WORK / "V19_TEXT_ORIGIN_VALIDATION.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_release_dir() -> None:
    if RELEASE_DIR.parent != WORK or not RELEASE_DIR.name.startswith(RELEASE_NAME):
        raise AssertionError(f"unsafe release directory: {RELEASE_DIR}")
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)


def lsp_entry(archive: A.Archive, name: str) -> A.Entry:
    hits = [entry for entry in archive.entries if entry.type_hash == LSP and entry.name == name]
    if len(hits) != 1:
        raise AssertionError(f"{name}: expected one LSP entry, found {len(hits)}")
    return hits[0]


def first_special_root(raw: bytes) -> tuple[int, int, bytes]:
    _, _, starts = V18.animation_area(raw)
    hits = []
    for ordinal, (lo, hi) in enumerate(zip(starts, starts[1:])):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == 0xFFFFFFFF:
            hits.append((ordinal, lo, hi, block))
    if not hits:
        raise AssertionError("special-root animation block not found")
    ordinal, lo, hi, block = hits[0]
    if ordinal != 0 or len(block) != 208:
        raise AssertionError(
            {"special_root_ordinal": ordinal, "offset": lo, "length": len(block)}
        )
    return lo, hi, block


def special_root_difference(base: bytes, donor: bytes) -> dict:
    base_lo, base_hi, before = first_special_root(base)
    donor_lo, donor_hi, after = first_special_root(donor)
    differences = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    if len(before) != len(after) or differences != [3, 107]:
        raise AssertionError(
            {
                "base_length": len(before),
                "donor_length": len(after),
                "differences": differences,
            }
        )
    edits = []
    for offset in (0, 104):
        old_value = struct.unpack_from(">I", before, offset)[0]
        new_value = struct.unpack_from(">I", after, offset)[0]
        if old_value != 0 or new_value != 1:
            raise AssertionError(f"special root +0x{offset:X}: {old_value} -> {new_value}")
        edits.append(
            {
                "block_offset": offset,
                "lsp_offset": base_lo + offset,
                "before_u32": old_value,
                "after_u32": new_value,
            }
        )
    return {
        "base_block_offset": base_lo,
        "base_block_end": base_hi,
        "donor_block_offset": donor_lo,
        "donor_block_end": donor_hi,
        "block_length": len(before),
        "target_id": "0xFFFFFFFF",
        "raw_byte_differences": differences,
        "edits": edits,
    }


def node_index_for_id(raw: bytes, wanted_name: str, wanted_id: int) -> int:
    _, names = V18.node_names(raw)
    hits = []
    for index, name in enumerate(names):
        if name != wanted_name:
            continue
        node_id = struct.unpack_from(
            ">I", raw, V18.NODE0 + index * V18.NODE_SIZE + 0x50
        )[0]
        if node_id == wanted_id:
            hits.append(index)
    if len(hits) != 1:
        raise AssertionError(
            {"name": wanted_name, "stable_id": wanted_id, "matching_indices": hits}
        )
    return hits[0]


def verify_shared_animation(
    base: bytes, donor: bytes, name: str, node_id: int, expected_count: int
) -> dict:
    base_index = node_index_for_id(base, name, node_id)
    donor_index = node_index_for_id(donor, name, node_id)
    base_blocks = V18.blocks_for_node(base, node_id)
    donor_blocks = V18.blocks_for_node(donor, node_id)
    if len(base_blocks) != expected_count or len(donor_blocks) != expected_count:
        raise AssertionError(
            {
                "name": name,
                "base_blocks": len(base_blocks),
                "donor_blocks": len(donor_blocks),
                "expected": expected_count,
            }
        )
    base_payloads = [block for _, _, block in base_blocks]
    donor_payloads = [block for _, _, block in donor_blocks]
    if base_payloads != donor_payloads:
        raise AssertionError(f"{name} ID {node_id}: V18 animation differs from SH")
    return {
        "name": name,
        "stable_id": node_id,
        "base_node_index": base_index,
        "donor_node_index": donor_index,
        "block_count": expected_count,
        "block_sha256": [sha(block) for block in base_payloads],
    }


def patch_special_root(base: bytes, donor: bytes) -> tuple[bytes, dict]:
    proof = special_root_difference(base, donor)
    base_lo, base_hi, _ = first_special_root(base)
    _, _, donor_block = first_special_root(donor)
    output = bytearray(base)
    for edit in proof["edits"]:
        absolute = edit["lsp_offset"]
        block_offset = edit["block_offset"]
        output[absolute:absolute + 4] = donor_block[block_offset:block_offset + 4]
    if bytes(output[base_lo:base_hi]) != donor_block:
        raise AssertionError("patched special-root block is not exact SH")
    changed = [index for index, pair in enumerate(zip(base, output)) if pair[0] != pair[1]]
    expected = [base_lo + 3, base_lo + 107]
    if changed != expected:
        raise AssertionError({"changed_raw_bytes": changed, "expected": expected})
    proof["changed_raw_byte_offsets"] = changed
    proof["raw_bytes_changed"] = len(changed)
    return bytes(output), proof


def two_player_corroboration() -> dict:
    utage_arc = A.parse_arc(UTAGE_2P)
    donor_arc = A.parse_arc(DONOR_2P)
    utage_lsp = A.unpack(lsp_entry(utage_arc, UTAGE_LSP_2P))
    donor_lsp = A.unpack(lsp_entry(donor_arc, DONOR_LSP_2P))
    utage_lo, _, utage_block = first_special_root(utage_lsp)
    donor_lo, _, donor_block = first_special_root(donor_lsp)
    differences = [
        index for index, pair in enumerate(zip(utage_block, donor_block)) if pair[0] != pair[1]
    ]
    if utage_block != donor_block:
        raise AssertionError({"2P special-root differences": differences})
    values = [struct.unpack_from(">I", utage_block, offset)[0] for offset in (0, 104)]
    if values != [1, 1]:
        raise AssertionError({"2P special-root enable values": values})
    return {
        "utage_archive": str(UTAGE_2P),
        "donor_archive": str(DONOR_2P),
        "utage_lsp_offset": utage_lo,
        "donor_lsp_offset": donor_lo,
        "block_length": len(utage_block),
        "enable_values": values,
        "blocks_exact": True,
    }


def create_backup(paths: list[Path]) -> None:
    if BACKUP.exists():
        with zipfile.ZipFile(BACKUP) as check:
            if check.testzip() is not None or len(check.infolist()) != len(paths):
                raise AssertionError("existing pre-V19 backup is invalid")
        return
    with zipfile.ZipFile(BACKUP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in paths:
            output.write(path, path.relative_to(UTAGE).as_posix())
    with zipfile.ZipFile(BACKUP) as check:
        if check.testzip() is not None or len(check.infolist()) != len(paths):
            raise AssertionError("pre-V19 backup verification failed")


def main() -> None:
    live_paths = [UTAGE / relative for relative in RELATIVES]
    if not all(path.is_file() for path in live_paths):
        raise FileNotFoundError("live cockpit1P pair is incomplete")
    live_hashes_before = {str(path): sha_file(path) for path in live_paths}
    if set(live_hashes_before.values()) != {EXPECTED_V18_ARC_SHA256}:
        raise AssertionError(
            {
                "expected_v18_sha256": EXPECTED_V18_ARC_SHA256,
                "live_hashes": live_hashes_before,
            }
        )
    create_backup(live_paths)
    remove_release_dir()
    RELEASE_DIR.mkdir(parents=True)

    donor_arc = A.parse_arc(DONOR_1P)
    donor_lsp = A.unpack(lsp_entry(donor_arc, DONOR_LSP_1P))
    shared_animation_proofs = None
    jobs = []
    outputs = []
    for relative, live_path in zip(RELATIVES, live_paths):
        base_arc = A.parse_arc(live_path)
        base_entry = lsp_entry(base_arc, UTAGE_LSP_1P)
        base_lsp = A.unpack(base_entry)
        if sha(base_lsp) != EXPECTED_V18_LSP_SHA256:
            raise AssertionError(
                {"path": str(live_path), "unexpected_v18_lsp_sha256": sha(base_lsp)}
            )

        proofs = [
            verify_shared_animation(base_lsp, donor_lsp, "Mess1", 182, 3),
            verify_shared_animation(base_lsp, donor_lsp, "3_0", 72, 2),
            verify_shared_animation(base_lsp, donor_lsp, "Line_U", 77, 3),
            verify_shared_animation(base_lsp, donor_lsp, "3_1", 76, 2),
        ]
        if shared_animation_proofs is None:
            shared_animation_proofs = proofs
        elif proofs != shared_animation_proofs:
            raise AssertionError("ENG/JPN animation proofs differ")

        patched_lsp, edit = patch_special_root(base_lsp, donor_lsp)
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
            if old.name != new.name or old.type_hash != new.type_hash:
                raise AssertionError("ARC entry identity changed")
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
        if rebuilt_lsp != patched_lsp or len(rebuilt_lsp) != len(base_lsp):
            raise AssertionError("patched LSP did not survive the ARC rebuild")
        for entry in output_arc.entries:
            A.unpack(entry)

        outputs.append(output_path)
        jobs.append(
            {
                "relative": relative.as_posix(),
                "base": str(live_path),
                "base_arc_sha256": sha(base_arc.data),
                "base_lsp_sha256": sha(base_lsp),
                "output": str(output_path),
                "output_arc_sha256": sha(rebuilt_raw),
                "output_lsp_sha256": sha(patched_lsp),
                "entry_count": len(output_arc.entries),
                "changed_arc_entries": changed_entries,
                "untouched_compressed_resources_preserved": True,
                "special_root_edit": edit,
            }
        )

    output_hashes = {sha_file(path) for path in outputs}
    if len(output_hashes) != 1:
        raise AssertionError("V19 ENG/JPN outputs are not byte-identical")

    report = {
        "status": "pass",
        "patch": "Utage Battle Dialogue V19 Text Origin",
        "diagnosis": (
            "Official SH screenshots show the panel height is fixed and V18 places its panel, "
            "portrait, and name plate correctly; only the glyph block is about 12-14 output pixels "
            "low. V18's dialogue geometry, SH FIM, SH TNF/CSA, and SH atlas are already exact. "
            "The remaining first 1P animation block contains two disabled special-root tracks "
            "targeting 0xFFFFFFFF where SH uses enabled=1. Utage 2P already matches SH with both "
            "tracks enabled. V19 changes only these two u32 enable values from 0 to 1."
        ),
        "base": "installed V18",
        "expected_v18_arc_sha256": EXPECTED_V18_ARC_SHA256,
        "expected_v18_lsp_sha256": EXPECTED_V18_LSP_SHA256,
        "pre_v19_runtime_backup": str(BACKUP),
        "pre_v19_runtime_backup_sha256": sha_file(BACKUP),
        "live_hashes_before": live_hashes_before,
        "donor_1p": str(DONOR_1P),
        "donor_1p_sha256": sha_file(DONOR_1P),
        "shared_sh_animation_proofs": shared_animation_proofs,
        "two_player_corroboration": two_player_corroboration(),
        "jobs": jobs,
        "mirrored_output_sha256": next(iter(output_hashes)),
        "offline_validation": "pass",
        "runtime_test": "required",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RELEASE_DIR / "VALIDATION_V19.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (RELEASE_DIR / "README_V19.txt").write_text(
        """Sengoku BASARA 3 Utage - Battle Dialogue V19 Text Origin

V19 corrects the final vertical text-origin mismatch seen after V18. Official
Samurai Heroes screenshots confirm the dialogue panel is a fixed-height plate;
the Utage V18 panel, portrait, and name plate are already correctly positioned,
but the rendered glyph block sits about 12-14 output pixels too low.

V18's panel geometry, relevant child animations, Samurai Heroes FIM metrics,
ASCII TNF/CSA, and atlas pages are already exact. The remaining 1P difference
is two disabled special-root animation records targeting ID FFFFFFFF. Official
SH enables both, and Utage's 2P layout already matches SH. V19 changes only
those two big-endian u32 values from 0 to 1. It does not alter coordinates,
textures, messages, fonts, FIM records, or cockpit2P.arc.

Merge PS3_GAME into the Utage game root and overwrite. Fully close RPCS3 and
cold boot m034/pl015 without a save state. Compare the same two-line Katakura
and three-line Masamune exchanges: the panel must remain where V18 placed it,
while the whole glyph block should move upward to the SH baseline. Also verify
portrait, name plate, mission banner, health/Basara meters, partner HUD, map,
and KOs counter.
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
            raise AssertionError("V19 package ZIP verification failed")
    zip_hash = sha_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_hash}  {OUTPUT_ZIP.name}\n", encoding="ascii")

    for relative, output_path in zip(RELATIVES, outputs):
        shutil.copy2(output_path, UTAGE / relative)
    live_hashes_after = {str(path): sha_file(path) for path in live_paths}
    if set(live_hashes_after.values()) != output_hashes:
        raise AssertionError("live V19 install hash mismatch")

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
