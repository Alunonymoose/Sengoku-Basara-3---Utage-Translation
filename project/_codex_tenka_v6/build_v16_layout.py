#!/usr/bin/env python3
"""V16 - port Samurai Heroes' Western in-battle message layout onto Utage.

Samurai Heroes ships two masters for the battle HUD: `id\\lsp\\jpn\\cockpit\\*`
(never shipped outside Japan) and `id\\lsp\\abr\\cockpit\\*`, the "abroad" build
Capcom widened and heightened for Latin text.  Utage never shipped in the West,
so it only has the `jpn` master, and its engine's route is hardcoded to `jpn`.
That is why SH's English dialogue overflows: the third line of a message and the
second line of a mission banner fall outside boxes sized for Japanese.

This copies SH's `abr` values for the two message groups onto Utage's `jpn`
master, node-for-node by name:

    3_0  3_0_0 Kao_L Kao_M Name Kamon 3_0_1 Mess1 Mess2 Mess3 Mess4 Mask
    3_1  Line_U Line_U Line_D Line_D MesJ_M MesJ_L MesJ_R

Only position (+0x00), geometry (+0x74) and UV (+0x84) are copied.  Offsets
+0x30 and +0x38 differ on essentially every node in both games - +0x30 is the
benign flag documented in the V8 KOs note, and +0x38 is a node link that would
point into the wrong tree, since Utage has 241 nodes to SH's 172.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"E:\Utage Patching New\_codex_tenka_v6")
import arc_tools as A
import arcbuild

LSP = 0x60DD1B16
NODE0, NODESZ = 16, 176
COPY = [(0x00, 8), (0x74, 16), (0x84, 16)]   # pos(2f), geo(4i), uv(4i)
GROUP = ["3_0", "3_0_0", "Kao_L", "Kao_M", "Name", "Kamon", "3_0_1",
         "Mess1", "Mess2", "Mess3", "Mess4", "Mask",
         "3_1", "Line_U", "Line_U", "Line_D", "Line_D",
         "MesJ_M", "MesJ_L", "MesJ_R"]

UTAGE = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")
SH = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom")

JOBS = [
    # (utage arcs to patch, utage lsp name, sh arc, sh lsp name)
    ([UTAGE / "eng/id/cockpit1P.arc", UTAGE / "jpn/id/cockpit1P.arc"],
     r"id\lsp\jpn\cockpit\cockpit",
     SH / "eng/id/cockpit1P.arc", r"id\lsp\abr\cockpit\cockpit"),
    ([UTAGE / "eng/id/cockpit2P.arc", UTAGE / "jpn/id/cockpit2P.arc"],
     r"id\lsp\jpn\cockpit\2p",
     SH / "eng/id/cockpit2P.arc", r"id\lsp\abr\cockpit\2p"),
]

STAGING = Path(__file__).parent / "V16_STAGING"
REPORT = Path(__file__).parent / "V16_REPORT.json"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def node_names(b):
    """Walk the length-prefixed (name, texture) table that follows the nodes."""
    count = struct.unpack_from(">H", b, 12)[0]
    # the table is a chained run of (u32 length, NUL-terminated string) pairs
    # starting at the root node's own name
    anchor = b"\x00\x00\x00\x08SysRoot\x00"
    i = b.find(anchor, NODE0 + count * NODESZ)
    if i < 0:
        raise AssertionError("SysRoot name table not found")
    names = []
    for k in range(count * 2):
        ln = struct.unpack_from(">I", b, i)[0]
        if k % 2 == 0:
            names.append(b[i + 4:i + 4 + ln - 1].decode("latin-1"))
        i += 4 + ln
    return count, names


def find_group(names):
    start = names.index(GROUP[0])
    got = names[start:start + len(GROUP)]
    if got != GROUP:
        raise AssertionError(f"group mismatch at {start}: {got}")
    return start


def port(utage_lsp: bytes, sh_lsp: bytes):
    ucount, unames = node_names(utage_lsp)
    scount, snames = node_names(sh_lsp)
    ui, si = find_group(unames), find_group(snames)
    out = bytearray(utage_lsp)
    changes = []
    for k, name in enumerate(GROUP):
        uo = NODE0 + (ui + k) * NODESZ
        so = NODE0 + (si + k) * NODESZ
        for off, size in COPY:
            before = bytes(out[uo + off:uo + off + size])
            after = sh_lsp[so + off:so + off + size]
            if before != after:
                out[uo + off:uo + off + size] = after
                changes.append({
                    "node": ui + k, "name": name, "field": f"0x{off:02X}",
                    "before": before.hex(), "after": after.hex(),
                })
    return bytes(out), {"utage_nodes": ucount, "sh_nodes": scount,
                        "utage_group_at": ui, "sh_group_at": si,
                        "fields_changed": len(changes), "changes": changes}


def main():
    if STAGING.exists():
        shutil.rmtree(STAGING)
    report = {"patch": "Utage V16 - SH abr in-battle message layout", "jobs": []}

    for utage_paths, ulsp, sh_path, slsp in JOBS:
        sh_arc = A.parse_arc(sh_path)
        sh_hits = [e for e in sh_arc.entries if e.type_hash == LSP and e.name == slsp]
        if len(sh_hits) != 1:
            raise AssertionError(f"{sh_path.name}: {len(sh_hits)} matches for {slsp}")
        sh_lsp = A.unpack(sh_hits[0])

        for up in utage_paths:
            if not up.exists():
                print(f"  skip (absent): {up}")
                continue
            arc = A.parse_arc(up)
            hits = [e for e in arc.entries if e.type_hash == LSP and e.name == ulsp]
            if len(hits) != 1:
                raise AssertionError(f"{up.name}: {len(hits)} matches for {ulsp}")
            entry = hits[0]
            old = A.unpack(entry)
            new, info = port(old, sh_lsp)
            if len(new) != len(old):
                raise AssertionError("LSP length changed")

            raw = arcbuild.build(arc, list(range(len(arc.entries))), {entry.index: new})
            rel = up.relative_to(UTAGE.parent.parent.parent.parent)
            outp = STAGING / rel
            outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_bytes(raw)

            # verify: only the one resource changed, everything else byte-identical
            chk = A.parse_arc(outp)
            if len(chk.entries) != len(arc.entries):
                raise AssertionError("entry count changed")
            diff = []
            for a, c in zip(arc.entries, chk.entries):
                if a.name != c.name or a.type_hash != c.type_hash:
                    raise AssertionError("entry identity changed")
                if A.unpack(a) != A.unpack(c):
                    diff.append(c.index)
            if diff != [entry.index]:
                raise AssertionError(f"unexpected changed entries: {diff}")
            if A.unpack(chk.entries[entry.index]) != new:
                raise AssertionError("LSP payload not installed")

            info.update({"source": str(up), "lsp": ulsp, "donor": str(sh_path),
                         "donor_lsp": slsp, "output": str(outp),
                         "lsp_before_sha256": sha(old), "lsp_after_sha256": sha(new)})
            report["jobs"].append(info)
            print(f"  {up.relative_to(UTAGE)}: {info['fields_changed']} fields on "
                  f"nodes {info['utage_group_at']}..{info['utage_group_at']+len(GROUP)-1}")

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"jobs": len(report["jobs"]),
                      "total_fields": sum(j["fields_changed"] for j in report["jobs"])},
                     indent=2))


if __name__ == "__main__":
    main()
