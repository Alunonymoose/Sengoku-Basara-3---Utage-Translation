#!/usr/bin/env python3
"""Read-only diagnostics for the remaining in-battle dialogue size selector."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


WORK = Path(__file__).resolve().parent
UTAGE = Path(r"E:\Utage Patching New")
SH = Path(r"E:\SAMURAI HEROES")
sys.path.insert(0, str(WORK))

import arc_tools as A  # noqa: E402
import build_v18_dialogue_alignment as V18  # noqa: E402


def get_lsp(path: Path, name: str) -> bytes:
    arc = A.parse_arc(path)
    return A.unpack(V18.lsp_entry(arc, name))


def block_rows(raw: bytes, limit: int = 20) -> list[dict]:
    _, _, starts = V18.animation_area(raw)
    rows = []
    for ordinal, (lo, hi) in enumerate(zip(starts, starts[1:])):
        block = raw[lo:hi]
        rows.append(
            {
                "ordinal": ordinal,
                "offset": lo,
                "length": len(block),
                "target_id": struct.unpack_from(">I", block, 0x6C)[0]
                if len(block) >= 0x70
                else None,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def first_global(raw: bytes) -> tuple[int, int, bytes]:
    _, _, starts = V18.animation_area(raw)
    hits = []
    for lo, hi in zip(starts, starts[1:]):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == 0xFFFFFFFF:
            hits.append((lo, hi, block))
    if not hits:
        raise AssertionError("no global animation block")
    return hits[0]


def compare_global(utage: bytes, donor: bytes) -> dict:
    ulo, uhi, ub = first_global(utage)
    slo, shi, sb = first_global(donor)
    differences = [index for index, pair in enumerate(zip(ub, sb)) if pair[0] != pair[1]]
    if len(ub) != len(sb):
        differences.extend(range(min(len(ub), len(sb)), max(len(ub), len(sb))))
    dword_differences = []
    for offset in range(0, min(len(ub), len(sb)), 4):
        before = struct.unpack_from(">I", ub, offset)[0]
        after = struct.unpack_from(">I", sb, offset)[0]
        if before != after:
            dword_differences.append(
                {"offset": offset, "utage_u32": before, "sh_u32": after}
            )
    return {
        "utage_offset": ulo,
        "sh_offset": slo,
        "utage_length": len(ub),
        "sh_length": len(sb),
        "raw_byte_differences": differences,
        "u32_differences": dword_differences,
    }


def node_report(utage: bytes, donor: bytes, name: str, expected_count: int) -> dict:
    ui, uid = V18.stable_node_id(utage, name)
    si, sid = V18.stable_node_id(donor, name)
    ublocks = V18.blocks_for_node(utage, uid)
    sblocks = V18.blocks_for_node(donor, sid)
    return {
        "name": name,
        "utage_index": ui,
        "sh_index": si,
        "utage_id": uid,
        "sh_id": sid,
        "utage_plus_30_u32": struct.unpack_from(">I", utage, V18.NODE0 + ui * V18.NODE_SIZE + 0x30)[0],
        "sh_plus_30_u32": struct.unpack_from(">I", donor, V18.NODE0 + si * V18.NODE_SIZE + 0x30)[0],
        "utage_block_count": len(ublocks),
        "sh_block_count": len(sblocks),
        "expected_block_count": expected_count,
        "blocks_exact": [block for _, _, block in ublocks] == [block for _, _, block in sblocks],
    }


def main() -> None:
    u1 = get_lsp(
        UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc",
        V18.UTAGE_LSP_NAME,
    )
    s1 = get_lsp(
        SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc",
        V18.DONOR_LSP_NAME,
    )
    u2 = get_lsp(
        UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc",
        V18.UTAGE_LSP_NAME,
    )
    s2 = get_lsp(
        SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc",
        V18.DONOR_LSP_NAME,
    )
    result = {
        "one_player": {
            "utage_length": len(u1),
            "sh_length": len(s1),
            "first_blocks_utage": block_rows(u1),
            "first_blocks_sh": block_rows(s1),
            "first_global_comparison": compare_global(u1, s1),
            "dialogue_nodes": [
                node_report(u1, s1, "Mess1", 3),
                node_report(u1, s1, "3_0", 2),
                node_report(u1, s1, "Line_U", 3),
                node_report(u1, s1, "3_1", 2),
            ],
        },
        "two_player_corroboration": {
            "utage_length": len(u2),
            "sh_length": len(s2),
            "first_global_comparison": compare_global(u2, s2),
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
