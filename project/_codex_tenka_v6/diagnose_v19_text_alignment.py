#!/usr/bin/env python3
"""Read-only comparison of Utage V18 and official SH dialogue text anchors."""

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


def lsp(path: Path, name: str) -> bytes:
    arc = A.parse_arc(path)
    return A.unpack(V18.lsp_entry(arc, name))


def first_global(raw: bytes) -> tuple[int, bytes]:
    _, _, starts = V18.animation_area(raw)
    for lo, hi in zip(starts, starts[1:]):
        block = raw[lo:hi]
        if len(block) >= 0x70 and struct.unpack_from(">I", block, 0x6C)[0] == 0xFFFFFFFF:
            return lo, block
    raise AssertionError("global block not found")


def global_diff(utage: bytes, sh: bytes) -> dict:
    ulo, ub = first_global(utage)
    slo, sb = first_global(sh)
    byte_differences = [i for i, pair in enumerate(zip(ub, sb)) if pair[0] != pair[1]]
    dword_differences = []
    for offset in range(0, min(len(ub), len(sb)), 4):
        before = struct.unpack_from(">I", ub, offset)[0]
        after = struct.unpack_from(">I", sb, offset)[0]
        if before != after:
            dword_differences.append(
                {"block_offset": offset, "utage_u32": before, "sh_u32": after}
            )
    return {
        "utage_offset": ulo,
        "sh_offset": slo,
        "utage_length": len(ub),
        "sh_length": len(sb),
        "raw_byte_differences": byte_differences,
        "u32_differences": dword_differences,
    }


def node(utage: bytes, sh: bytes, name: str) -> dict:
    ui, uid = V18.stable_node_id(utage, name)
    si, sid = V18.stable_node_id(sh, name)
    ub = V18.blocks_for_node(utage, uid)
    sb = V18.blocks_for_node(sh, sid)
    node_byte_differences = []
    unode = utage[V18.NODE0 + ui * V18.NODE_SIZE:V18.NODE0 + (ui + 1) * V18.NODE_SIZE]
    snode = sh[V18.NODE0 + si * V18.NODE_SIZE:V18.NODE0 + (si + 1) * V18.NODE_SIZE]
    for offset, pair in enumerate(zip(unode, snode)):
        if pair[0] != pair[1]:
            node_byte_differences.append(offset)
    return {
        "name": name,
        "utage_index": ui,
        "sh_index": si,
        "stable_id": uid,
        "sh_stable_id": sid,
        "node_byte_differences": node_byte_differences,
        "utage_plus_30_u32": struct.unpack_from(">I", unode, 0x30)[0],
        "sh_plus_30_u32": struct.unpack_from(">I", snode, 0x30)[0],
        "utage_block_count": len(ub),
        "sh_block_count": len(sb),
        "animation_blocks_exact": [x for _, _, x in ub] == [x for _, _, x in sb],
    }


def main() -> None:
    u1 = lsp(
        UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc",
        V18.UTAGE_LSP_NAME,
    )
    s1 = lsp(
        SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit1P.arc",
        V18.DONOR_LSP_NAME,
    )
    u2 = lsp(
        UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc",
        r"id\lsp\jpn\cockpit\2p",
    )
    s2 = lsp(
        SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id\cockpit2P.arc",
        r"id\lsp\abr\cockpit\2p",
    )
    print(
        json.dumps(
            {
                "one_player": {
                    "global": global_diff(u1, s1),
                    "nodes": [
                        node(u1, s1, "Mess1"),
                        node(u1, s1, "3_0"),
                        node(u1, s1, "Line_U"),
                        node(u1, s1, "3_1"),
                    ],
                },
                "two_player_corroboration": {"global": global_diff(u2, s2)},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
