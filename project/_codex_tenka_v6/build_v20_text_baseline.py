#!/usr/bin/env python3
"""V20 - raise generated 1P dialogue text by 8 LSP units (12 px at 1080p).

V19's SH special-root flags produced no visible baseline movement.  Runtime
frame measurement shows the Utage glyph block is 12 output pixels below the
official SH frame, exactly 8 units in the cockpit's 1280x720 coordinate space.

The generated text is anchored to parent node ``3`` (stable ID 71), while the
panel artwork lives in its two visual children ``3_0`` and ``3_1``.  V20 moves
the parent up 8 units, then adds 8 units to both visual child roots and every
active ``3_0`` Y key.  Therefore the visual world transforms are unchanged,
but the parent-level generated-text origin moves upward by 8 units.
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
sys.path.insert(0, str(WORK))

import arc_tools as A  # noqa: E402
import build_v18_dialogue_alignment as V18  # noqa: E402


LSP = 0x60DD1B16
EXPECTED_V19_ARC_SHA256 = "6e02355a956d5a645edc908fbc2d5c0c461dd65caed8e9ab05b9e6d996c262c9"
EXPECTED_V19_LSP_SHA256 = "aadd36fbf00348b372538b86bf649ccf2e0cca85dffd583e97ecb69e87d6c097"

RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
LSP_NAME = r"id\lsp\jpn\cockpit\cockpit"
BACKUP = WORK / "V20_BACKUP_cockpit1P_pre_v20.zip"
RELEASE_NAME = "Utage_Battle_Dialogue_V20_TEXT_BASELINE_COMPENSATION_ROOT_READY"
RELEASE_DIR = WORK / RELEASE_NAME
OUTPUT_ZIP = WORK / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = WORK / f"{RELEASE_NAME}.zip.sha256"
REPORT = WORK / "V20_TEXT_BASELINE_VALIDATION.json"

SHIFT_LSP_UNITS = 8.0
OUTPUT_SCALE_1080P = 1.5
MEASURED_OUTPUT_SHIFT = 12


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lsp_entry(archive: A.Archive) -> A.Entry:
    hits = [entry for entry in archive.entries if entry.type_hash == LSP and entry.name == LSP_NAME]
    if len(hits) != 1:
        raise AssertionError(f"{LSP_NAME}: expected one LSP entry, found {len(hits)}")
    return hits[0]


def node_index(raw: bytes, name: str, stable_id: int) -> int:
    _, names = V18.node_names(raw)
    hits = []
    for index, value in enumerate(names):
        if value != name:
            continue
        node_id = struct.unpack_from(
            ">I", raw, V18.NODE0 + index * V18.NODE_SIZE + 0x50
        )[0]
        if node_id == stable_id:
            hits.append(index)
    if len(hits) != 1:
        raise AssertionError({"name": name, "stable_id": stable_id, "hits": hits})
    return hits[0]


def node_values(raw: bytes, name: str, stable_id: int) -> dict:
    index = node_index(raw, name, stable_id)
    offset = V18.NODE0 + index * V18.NODE_SIZE
    x, y = struct.unpack_from(">2f", raw, offset)
    parent = struct.unpack_from(">I", raw, offset + 0x38)[0]
    return {
        "name": name,
        "stable_id": stable_id,
        "index": index,
        "record_offset": offset,
        "x": x,
        "y": y,
        "parent_index": parent,
    }


def verify_v19_special_root(raw: bytes) -> dict:
    _, _, starts = V18.animation_area(raw)
    for ordinal, (lo, hi) in enumerate(zip(starts, starts[1:])):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == 0xFFFFFFFF:
            if ordinal != 0 or len(block) != 208:
                raise AssertionError({"ordinal": ordinal, "offset": lo, "length": len(block)})
            values = [struct.unpack_from(">I", block, offset)[0] for offset in (0, 104)]
            if values != [1, 1]:
                raise AssertionError({"V19 special-root values": values})
            return {"offset": lo, "length": len(block), "enable_values": values}
    raise AssertionError("V19 special-root block absent")


def patch_baseline(base: bytes) -> tuple[bytes, dict]:
    root = node_values(base, "3", 71)
    panel = node_values(base, "3_0", 72)
    auxiliary = node_values(base, "3_1", 76)
    if root["index"] != 116 or root["parent_index"] != 0 or root["y"] != 330.0:
        raise AssertionError({"unexpected root": root})
    if panel["index"] != 117 or panel["parent_index"] != root["index"] or panel["y"] != 8.0:
        raise AssertionError({"unexpected panel root": panel})
    if auxiliary["index"] != 129 or auxiliary["parent_index"] != root["index"] or auxiliary["y"] != 0.0:
        raise AssertionError({"unexpected auxiliary root": auxiliary})

    panel_blocks = V18.blocks_for_node(base, 72)
    if len(panel_blocks) != 2 or any(len(block) != 280 for _, _, block in panel_blocks):
        raise AssertionError({"3_0 block lengths": [len(block) for _, _, block in panel_blocks]})

    output = bytearray(base)
    edits = []

    def write_f32(absolute: int, expected: float, replacement: float, label: str) -> None:
        actual = struct.unpack_from(">f", base, absolute)[0]
        if actual != expected:
            raise AssertionError(f"{label}: expected {expected}, found {actual}")
        output[absolute:absolute + 4] = struct.pack(">f", replacement)
        edits.append(
            {
                "label": label,
                "lsp_offset": absolute,
                "before_f32": expected,
                "after_f32": replacement,
            }
        )

    write_f32(root["record_offset"] + 4, 330.0, 322.0, "node 3 static Y")
    write_f32(panel["record_offset"] + 4, 8.0, 16.0, "node 3_0 static Y compensation")
    write_f32(auxiliary["record_offset"] + 4, 0.0, 8.0, "node 3_1 static Y compensation")
    for block_index, (lo, _, block) in enumerate(panel_blocks):
        for block_offset in (0x88, 0xA0):
            value = struct.unpack_from(">f", block, block_offset)[0]
            if value != 3.0:
                raise AssertionError(
                    f"3_0 animation block {block_index} +0x{block_offset:X}: {value}"
                )
            write_f32(
                lo + block_offset,
                3.0,
                11.0,
                f"3_0 animation block {block_index} Y compensation +0x{block_offset:X}",
            )

    patched = bytes(output)
    changed = [index for index, pair in enumerate(zip(base, patched)) if pair[0] != pair[1]]
    expected_changed = sorted(
        edit["lsp_offset"] + delta
        for edit in edits
        for delta in range(4)
        if base[edit["lsp_offset"] + delta] != patched[edit["lsp_offset"] + delta]
    )
    if changed != expected_changed:
        raise AssertionError({"changed": changed, "expected": expected_changed})

    after_root = node_values(patched, "3", 71)
    after_panel = node_values(patched, "3_0", 72)
    after_auxiliary = node_values(patched, "3_1", 76)
    after_blocks = V18.blocks_for_node(patched, 72)
    after_keys = [
        struct.unpack_from(">f", block, offset)[0]
        for _, _, block in after_blocks
        for offset in (0x88, 0xA0)
    ]
    if after_keys != [11.0, 11.0, 11.0, 11.0]:
        raise AssertionError({"after 3_0 Y keys": after_keys})

    world_before = {
        "text_anchor": root["y"],
        "panel_static": root["y"] + panel["y"],
        "panel_animated": root["y"] + 3.0,
        "auxiliary_static": root["y"] + auxiliary["y"],
    }
    world_after = {
        "text_anchor": after_root["y"],
        "panel_static": after_root["y"] + after_panel["y"],
        "panel_animated": after_root["y"] + 11.0,
        "auxiliary_static": after_root["y"] + after_auxiliary["y"],
    }
    if world_after["text_anchor"] != world_before["text_anchor"] - SHIFT_LSP_UNITS:
        raise AssertionError({"world_before": world_before, "world_after": world_after})
    for key in ("panel_static", "panel_animated", "auxiliary_static"):
        if world_after[key] != world_before[key]:
            raise AssertionError({"world_before": world_before, "world_after": world_after})

    return patched, {
        "lsp_shift_units": SHIFT_LSP_UNITS,
        "expected_output_pixels_at_1080p": SHIFT_LSP_UNITS * OUTPUT_SCALE_1080P,
        "measured_v19_to_sh_output_pixels": MEASURED_OUTPUT_SHIFT,
        "nodes_before": [root, panel, auxiliary],
        "nodes_after": [after_root, after_panel, after_auxiliary],
        "world_y_before": world_before,
        "world_y_after": world_after,
        "edits": edits,
        "raw_bytes_changed": len(changed),
        "changed_raw_byte_offsets": changed,
    }


def create_backup(paths: list[Path]) -> None:
    if BACKUP.exists():
        with zipfile.ZipFile(BACKUP) as check:
            if check.testzip() is not None or len(check.infolist()) != len(paths):
                raise AssertionError("existing pre-V20 backup is invalid")
        return
    with zipfile.ZipFile(BACKUP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in paths:
            output.write(path, path.relative_to(UTAGE).as_posix())
    with zipfile.ZipFile(BACKUP) as check:
        if check.testzip() is not None or len(check.infolist()) != len(paths):
            raise AssertionError("pre-V20 backup verification failed")


def remove_release_dir() -> None:
    if RELEASE_DIR.parent != WORK or RELEASE_DIR.name != RELEASE_NAME:
        raise AssertionError(f"unsafe release directory: {RELEASE_DIR}")
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)


def main() -> None:
    live_paths = [UTAGE / relative for relative in RELATIVES]
    live_hashes_before = {str(path): sha_file(path) for path in live_paths}
    if set(live_hashes_before.values()) != {EXPECTED_V19_ARC_SHA256}:
        raise AssertionError(
            {"expected_v19": EXPECTED_V19_ARC_SHA256, "live_hashes": live_hashes_before}
        )
    create_backup(live_paths)
    remove_release_dir()
    RELEASE_DIR.mkdir(parents=True)

    jobs = []
    outputs = []
    for relative, live_path in zip(RELATIVES, live_paths):
        base_arc = A.parse_arc(live_path)
        base_entry = lsp_entry(base_arc)
        base_lsp = A.unpack(base_entry)
        if sha(base_lsp) != EXPECTED_V19_LSP_SHA256:
            raise AssertionError({"path": str(live_path), "lsp_sha256": sha(base_lsp)})
        special_root = verify_v19_special_root(base_lsp)
        patched_lsp, edit_report = patch_baseline(base_lsp)
        if verify_v19_special_root(patched_lsp) != special_root:
            raise AssertionError("V19 special-root block changed")

        rebuilt = A.rebuild(base_arc, {base_entry.index: patched_lsp})
        output_path = RELEASE_DIR / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(rebuilt)
        output_arc = A.parse_arc(output_path)
        if len(output_arc.entries) != len(base_arc.entries):
            raise AssertionError("ARC entry count changed")
        changed_entries = []
        compressed_preserved = True
        for before, after in zip(base_arc.entries, output_arc.entries):
            if before.name != after.name or before.type_hash != after.type_hash:
                raise AssertionError("ARC entry identity changed")
            if A.unpack(before) != A.unpack(after):
                changed_entries.append(after.index)
            elif before.compressed != after.compressed:
                compressed_preserved = False
        if changed_entries != [base_entry.index] or not compressed_preserved:
            raise AssertionError(
                {"changed_entries": changed_entries, "compressed_preserved": compressed_preserved}
            )
        rebuilt_lsp = A.unpack(output_arc.entries[base_entry.index])
        if rebuilt_lsp != patched_lsp or len(rebuilt_lsp) != len(base_lsp):
            raise AssertionError("patched LSP rebuild mismatch")
        for entry in output_arc.entries:
            A.unpack(entry)

        outputs.append(output_path)
        jobs.append(
            {
                "relative": relative.as_posix(),
                "base_arc_sha256": sha(base_arc.data),
                "base_lsp_sha256": sha(base_lsp),
                "output_arc_sha256": sha(rebuilt),
                "output_lsp_sha256": sha(patched_lsp),
                "entry_count": len(output_arc.entries),
                "changed_arc_entries": changed_entries,
                "untouched_compressed_resources_preserved": True,
                "special_root_preserved": special_root,
                "baseline_compensation": edit_report,
            }
        )

    output_hashes = {sha_file(path) for path in outputs}
    if len(output_hashes) != 1:
        raise AssertionError("V20 ENG/JPN outputs are not byte-identical")

    report = {
        "status": "pass",
        "patch": "Utage Battle Dialogue V20 Text Baseline Compensation",
        "diagnosis": (
            "V19's special-root flag port had no visible baseline effect. Pixel analysis shows "
            "V19's glyph rows are unchanged from V18 and sit 12 pixels below official SH at "
            "1920x1080. This equals 8 units in the 1280x720 cockpit coordinate space. V20 moves "
            "parent node 3 up 8 units, then applies equal opposite compensation to both visual "
            "child roots and all active 3_0 Y keys. The generated-text anchor moves up while the "
            "panel, portrait, name plate, and auxiliary visuals retain their world Y positions."
        ),
        "base": "installed V19",
        "expected_v19_arc_sha256": EXPECTED_V19_ARC_SHA256,
        "expected_v19_lsp_sha256": EXPECTED_V19_LSP_SHA256,
        "pre_v20_runtime_backup": str(BACKUP),
        "pre_v20_runtime_backup_sha256": sha_file(BACKUP),
        "live_hashes_before": live_hashes_before,
        "jobs": jobs,
        "mirrored_output_sha256": next(iter(output_hashes)),
        "cockpit2p_modified": False,
        "offline_validation": "pass",
        "runtime_test": "required",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RELEASE_DIR / "VALIDATION_V20.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (RELEASE_DIR / "README_V20.txt").write_text(
        """Sengoku BASARA 3 Utage - Battle Dialogue V20 Text Baseline

V19 did not visibly move the dialogue glyphs. Image measurement against the
official Samurai Heroes frame places the remaining offset at 12 pixels at
1920x1080, equal to 8 units in the cockpit's 1280x720 coordinate system.

V20 moves parent dialogue node 3 upward by 8 units. It applies equal opposite
compensation to visual roots 3_0 and 3_1 and all four active 3_0 Y keys. This
preserves the current panel, portrait, name plate, and auxiliary visual world
positions while raising only the parent-level generated-text origin. V19's SH
special-root block is retained. No message, FIM, font, texture, or cockpit2P
resource is modified.

Fully close RPCS3 and cold boot m034/pl015 without a save state. Compare the
same two-line and three-line exchanges. The whole glyph block should move up
12 pixels at 1080p while the panel and portrait remain in their V19 positions.
Verify the third line is clear of the panel bottom and check the mission banner,
health/Basara meters, partner HUD, minimap, and KOs counter.
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
            raise AssertionError("V20 package ZIP verification failed")
    zip_hash = sha_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_hash}  {OUTPUT_ZIP.name}\n", encoding="ascii")

    for relative, output_path in zip(RELATIVES, outputs):
        shutil.copy2(output_path, UTAGE / relative)
    live_hashes_after = {str(path): sha_file(path) for path in live_paths}
    if set(live_hashes_after.values()) != output_hashes:
        raise AssertionError("live V20 install hash mismatch")

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
