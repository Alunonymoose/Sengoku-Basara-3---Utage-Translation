#!/usr/bin/env python3
"""V21 - move the generated 1P dialogue baseline down exactly 1 px at 1080p."""

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
EXPECTED_V20_ARC_SHA256 = "d57c2929b52e574dc8bda16f168e4b28ea2edcd2965fbd45569d2dde856fbd98"
EXPECTED_V20_LSP_SHA256 = "a8fcbd8134fdba3aec8147ead8f7e015ea537839c962d2338ce14bd53d90a403"
RELATIVES = [
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc"),
    Path(r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id\cockpit1P.arc"),
]
LSP_NAME = r"id\lsp\jpn\cockpit\cockpit"
BACKUP = WORK / "V21_BACKUP_cockpit1P_pre_v21.zip"
RELEASE_NAME = "Utage_Battle_Dialogue_V21_ONE_PIXEL_TUNE_ROOT_READY"
RELEASE_DIR = WORK / RELEASE_NAME
OUTPUT_ZIP = WORK / f"{RELEASE_NAME}.zip"
OUTPUT_SHA = WORK / f"{RELEASE_NAME}.zip.sha256"
REPORT = WORK / "V21_ONE_PIXEL_TUNE_VALIDATION.json"

DELTA_LSP = 2.0 / 3.0
EXPECTED_OUTPUT_PIXELS = DELTA_LSP * 1.5


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entry(arc: A.Archive) -> A.Entry:
    hits = [e for e in arc.entries if e.type_hash == LSP and e.name == LSP_NAME]
    if len(hits) != 1:
        raise AssertionError({"LSP matches": len(hits)})
    return hits[0]


def node_y_offset(index: int) -> int:
    return V18.NODE0 + index * V18.NODE_SIZE + 4


def f32(raw: bytes, offset: int) -> float:
    return struct.unpack_from(">f", raw, offset)[0]


def patch(raw: bytes) -> tuple[bytes, dict]:
    static = {
        "node 3 text anchor": (node_y_offset(116), 322.0, 322.0 + DELTA_LSP),
        "node 3_0 visual compensation": (node_y_offset(117), 16.0, 16.0 - DELTA_LSP),
        "node 3_1 visual compensation": (node_y_offset(129), 8.0, 8.0 - DELTA_LSP),
    }
    blocks = V18.blocks_for_node(raw, 72)
    if len(blocks) != 2 or any(len(block) != 280 for _, _, block in blocks):
        raise AssertionError({"3_0 blocks": [len(block) for _, _, block in blocks]})
    animation = {}
    for block_index, (lo, _, block) in enumerate(blocks):
        for block_offset in (0x88, 0xA0):
            if struct.unpack_from(">f", block, block_offset)[0] != 11.0:
                raise AssertionError(f"unexpected V20 key in block {block_index}")
            animation[f"3_0 block {block_index} +0x{block_offset:X}"] = (
                lo + block_offset,
                11.0,
                11.0 - DELTA_LSP,
            )

    output = bytearray(raw)
    edits = []
    for label, (offset, before, after) in {**static, **animation}.items():
        actual = f32(raw, offset)
        if actual != before:
            raise AssertionError({"label": label, "expected": before, "actual": actual})
        output[offset:offset + 4] = struct.pack(">f", after)
        edits.append(
            {
                "label": label,
                "lsp_offset": offset,
                "before_f32": before,
                "after_f32": f32(bytes(output), offset),
            }
        )
    patched = bytes(output)
    changed = [i for i, pair in enumerate(zip(raw, patched)) if pair[0] != pair[1]]
    expected = sorted(
        edit["lsp_offset"] + delta
        for edit in edits
        for delta in range(4)
        if raw[edit["lsp_offset"] + delta] != patched[edit["lsp_offset"] + delta]
    )
    if changed != expected:
        raise AssertionError({"changed": changed, "expected": expected})

    before_root, before_panel, before_aux = 322.0, 16.0, 8.0
    after_root = f32(patched, node_y_offset(116))
    after_panel = f32(patched, node_y_offset(117))
    after_aux = f32(patched, node_y_offset(129))
    after_key = f32(patched, blocks[0][0] + 0x88)
    world_before = [before_root + before_panel, before_root + 11.0, before_root + before_aux]
    world_after = [after_root + after_panel, after_root + after_key, after_root + after_aux]
    if any(abs(a - b) > 0.0001 for a, b in zip(world_before, world_after)):
        raise AssertionError({"world_before": world_before, "world_after": world_after})
    if abs((after_root - before_root) * 1.5 - 1.0) > 0.0001:
        raise AssertionError({"unexpected output-pixel shift": (after_root - before_root) * 1.5})

    _, _, starts = V18.animation_area(patched)
    special = patched[starts[0]:starts[1]]
    special_values = [struct.unpack_from(">I", special, offset)[0] for offset in (0, 104)]
    if len(special) != 208 or special_values != [1, 1]:
        raise AssertionError({"special_length": len(special), "special_values": special_values})

    return patched, {
        "direction": "down",
        "lsp_units": DELTA_LSP,
        "expected_output_pixels_at_1080p": EXPECTED_OUTPUT_PIXELS,
        "text_anchor_before": before_root,
        "text_anchor_after": after_root,
        "visual_world_y_before": world_before,
        "visual_world_y_after": world_after,
        "edits": edits,
        "changed_raw_byte_offsets": changed,
        "raw_bytes_changed": len(changed),
        "v19_special_root_preserved": special_values,
    }


def backup(paths: list[Path]) -> None:
    if BACKUP.exists():
        with zipfile.ZipFile(BACKUP) as check:
            if check.testzip() is not None or len(check.infolist()) != 2:
                raise AssertionError("existing V21 backup invalid")
        return
    with zipfile.ZipFile(BACKUP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in paths:
            out.write(path, path.relative_to(UTAGE).as_posix())
    with zipfile.ZipFile(BACKUP) as check:
        if check.testzip() is not None or len(check.infolist()) != 2:
            raise AssertionError("V21 backup invalid")


def main() -> None:
    live_paths = [UTAGE / relative for relative in RELATIVES]
    live_before = {str(path): sha_file(path) for path in live_paths}
    if set(live_before.values()) != {EXPECTED_V20_ARC_SHA256}:
        raise AssertionError({"expected": EXPECTED_V20_ARC_SHA256, "live": live_before})
    backup(live_paths)
    if RELEASE_DIR.exists():
        if RELEASE_DIR.parent != WORK or RELEASE_DIR.name != RELEASE_NAME:
            raise AssertionError(f"unsafe release path: {RELEASE_DIR}")
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    outputs = []
    jobs = []
    for relative, live_path in zip(RELATIVES, live_paths):
        base_arc = A.parse_arc(live_path)
        base_entry = entry(base_arc)
        base_lsp = A.unpack(base_entry)
        if sha(base_lsp) != EXPECTED_V20_LSP_SHA256:
            raise AssertionError({"unexpected V20 LSP": sha(base_lsp)})
        patched_lsp, edit = patch(base_lsp)
        rebuilt = A.rebuild(base_arc, {base_entry.index: patched_lsp})
        output_path = RELEASE_DIR / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(rebuilt)
        output_arc = A.parse_arc(output_path)
        changed_entries = []
        compressed_preserved = True
        for before, after in zip(base_arc.entries, output_arc.entries):
            if before.name != after.name or before.type_hash != after.type_hash:
                raise AssertionError("ARC identity drift")
            if A.unpack(before) != A.unpack(after):
                changed_entries.append(after.index)
            elif before.compressed != after.compressed:
                compressed_preserved = False
        if changed_entries != [18] or not compressed_preserved:
            raise AssertionError(
                {"changed_entries": changed_entries, "compressed_preserved": compressed_preserved}
            )
        if A.unpack(output_arc.entries[18]) != patched_lsp or len(patched_lsp) != len(base_lsp):
            raise AssertionError("rebuilt LSP mismatch")
        for arc_entry in output_arc.entries:
            A.unpack(arc_entry)
        outputs.append(output_path)
        jobs.append(
            {
                "relative": relative.as_posix(),
                "base_arc_sha256": sha(base_arc.data),
                "base_lsp_sha256": sha(base_lsp),
                "output_arc_sha256": sha(rebuilt),
                "output_lsp_sha256": sha(patched_lsp),
                "changed_arc_entries": changed_entries,
                "untouched_compressed_resources_preserved": True,
                "one_pixel_tune": edit,
            }
        )
    hashes = {sha_file(path) for path in outputs}
    if len(hashes) != 1:
        raise AssertionError("V21 outputs not mirrored")

    report = {
        "status": "pass",
        "patch": "Utage Battle Dialogue V21 One Pixel Tune",
        "diagnosis": (
            "Runtime confirmed V20 is approximately one output pixel high. V21 moves parent "
            "text anchor node 3 down exactly 2/3 LSP unit, which scales to one pixel at 1080p, "
            "and applies the inverse delta to both visual roots and all active 3_0 Y keys so "
            "the panel, portrait, name plate, and auxiliary visual world positions do not move."
        ),
        "base": "installed V20",
        "live_hashes_before": live_before,
        "pre_v21_backup": str(BACKUP),
        "pre_v21_backup_sha256": sha_file(BACKUP),
        "jobs": jobs,
        "mirrored_output_sha256": next(iter(hashes)),
        "cockpit2p_modified": False,
        "offline_validation": "pass",
        "runtime_test": "required",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RELEASE_DIR / "VALIDATION_V21.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RELEASE_DIR / "README_V21.txt").write_text(
        """Sengoku BASARA 3 Utage - Battle Dialogue V21 One-Pixel Tune

V21 moves the generated dialogue text down exactly one output pixel at 1080p.
The parent text anchor moves by 2/3 LSP unit and equal inverse compensation is
applied to both visual roots and all active panel Y keys. The panel, portrait,
speaker-name plate, and auxiliary visuals retain their V20 world positions.

No message, FIM, font, texture, or cockpit2P resource is modified. Fully close
RPCS3 and cold boot the same two- and three-line exchanges without a save state.
""",
        encoding="utf-8",
    )
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    files = sorted(path for path in RELEASE_DIR.rglob("*") if path.is_file())
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in files:
            out.write(path, path.relative_to(RELEASE_DIR).as_posix())
    with zipfile.ZipFile(OUTPUT_ZIP) as check:
        if check.testzip() is not None or len(check.infolist()) != len(files):
            raise AssertionError("V21 ZIP invalid")
    zip_hash = sha_file(OUTPUT_ZIP)
    OUTPUT_SHA.write_text(f"{zip_hash}  {OUTPUT_ZIP.name}\n", encoding="ascii")
    for relative, output_path in zip(RELATIVES, outputs):
        shutil.copy2(output_path, UTAGE / relative)
    live_after = {str(path): sha_file(path) for path in live_paths}
    if set(live_after.values()) != hashes:
        raise AssertionError("live V21 install mismatch")
    print(
        json.dumps(
            {
                "status": "pass",
                "report": str(REPORT),
                "zip": str(OUTPUT_ZIP),
                "zip_sha256": zip_hash,
                "mirrored_cockpit1p_sha256": next(iter(hashes)),
                "live_hashes_after": live_after,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
