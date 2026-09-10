#!/usr/bin/env python3
"""Validated V19 runner with corrected 2P special-root corroboration.

The direct builder's first safety run proved that the Utage and SH 2P blocks
are exact at [1, 0], rather than [1, 1].  This runner preserves that guard,
uses SH's [1, 1] pair only for 1P, and refreshes the packaged wording/hash.
"""

from __future__ import annotations

import json
import struct
import zipfile

import build_v19_text_origin as B


def corrected_two_player_corroboration() -> dict:
    utage_arc = B.A.parse_arc(B.UTAGE_2P)
    donor_arc = B.A.parse_arc(B.DONOR_2P)
    utage_lsp = B.A.unpack(B.lsp_entry(utage_arc, B.UTAGE_LSP_2P))
    donor_lsp = B.A.unpack(B.lsp_entry(donor_arc, B.DONOR_LSP_2P))
    utage_lo, _, utage_block = B.first_special_root(utage_lsp)
    donor_lo, _, donor_block = B.first_special_root(donor_lsp)
    differences = [
        index for index, pair in enumerate(zip(utage_block, donor_block)) if pair[0] != pair[1]
    ]
    if utage_block != donor_block:
        raise AssertionError({"2P special-root differences": differences})
    values = [struct.unpack_from(">I", utage_block, offset)[0] for offset in (0, 104)]
    if values != [1, 0]:
        raise AssertionError({"2P special-root enable values": values})
    return {
        "utage_archive": str(B.UTAGE_2P),
        "donor_archive": str(B.DONOR_2P),
        "utage_lsp_offset": utage_lo,
        "donor_lsp_offset": donor_lo,
        "block_length": len(utage_block),
        "enable_values": values,
        "blocks_exact": True,
    }


def correct_packaged_wording() -> str:
    replacement = (
        "Utage 2P already matches SH on its layout-specific [1, 0] pair. "
        "V19 changes only the two 1P u32 enable values from 0 to 1."
    )
    for path in (B.REPORT, B.RELEASE_DIR / "VALIDATION_V19.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["diagnosis"] = data["diagnosis"].replace(
            "Utage 2P already matches SH with both tracks enabled. "
            "V19 changes only these two u32 enable values from 0 to 1.",
            replacement,
        )
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    readme = B.RELEASE_DIR / "README_V19.txt"
    text = readme.read_text(encoding="utf-8").replace(
        "Official\nSH enables both, and Utage's 2P layout already matches SH. V19 changes only\n"
        "those two big-endian u32 values from 0 to 1.",
        "Official\nSH enables both in 1P; Utage's 2P layout already matches SH on its [1, 0]\n"
        "pair. V19 changes only the two 1P big-endian u32 values from 0 to 1.",
    )
    readme.write_text(text, encoding="utf-8")

    files = sorted(path for path in B.RELEASE_DIR.rglob("*") if path.is_file())
    if B.OUTPUT_ZIP.exists():
        B.OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(B.OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, path.relative_to(B.RELEASE_DIR).as_posix())
    with zipfile.ZipFile(B.OUTPUT_ZIP) as check:
        if check.testzip() is not None or len(check.infolist()) != len(files):
            raise AssertionError("corrected V19 package ZIP verification failed")
    final_hash = B.sha_file(B.OUTPUT_ZIP)
    B.OUTPUT_SHA.write_text(f"{final_hash}  {B.OUTPUT_ZIP.name}\n", encoding="ascii")
    return final_hash


B.two_player_corroboration = corrected_two_player_corroboration
B.main()
print(json.dumps({"corrected_package_sha256": correct_packaged_wording()}, indent=2))
