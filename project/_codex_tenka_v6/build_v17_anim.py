#!/usr/bin/env python3
"""V17 - port Samurai Heroes' three-line message-window animation state.

The LSP animation section is a flat sequence of blocks, one per entry in the
name table that follows the node array (count = u16 at header +14).  The first
entries are the message-window clips:

    Ani 0_0_0  Mess1 Mess3 Mess4 Name Kamon     1-line window
    Ani 0_0_1  Mess1 Mess3 Mess4 Name Kamon     2-line window
    Ani 0_0_2  Mess1 Mess3 Mess4 Name Kamon     3-line window

Utage and Samurai Heroes are byte-identical through `Ani 0_0_1` and into
`Ani 0_0_2`'s Mess1/Mess3 tracks.  They part company on `Mess4`: SH carries a
full 448-byte track where Utage has a 104-byte stub, and SH keys scale on
`Name` where Utage has none.  Capcom authored that third state for the Western
release; Utage, whose own dialogue never exceeds two lines, never got it - so
the third line of Samurai Heroes' English falls out of the box.

This replaces Utage's whole `Ani 0_0_2` group (the clip plus its five targets)
with SH's.  Blocks are self-describing and walked sequentially - no offset table
references them (checked: no monotonic pointer field in the node records) - so
the group can change length; everything after it simply shifts.
"""
from __future__ import annotations

import hashlib
import json
import re
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
CLIP = "Ani 0_0_2"
TARGETS = ["Mess1", "Mess3", "Mess4", "Name", "Kamon"]
BOUNDARY = re.compile(rb"\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00")

UTAGE = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")
SH = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom")

JOBS = [
    ([UTAGE / "eng/id/cockpit1P.arc", UTAGE / "jpn/id/cockpit1P.arc"],
     r"id\lsp\jpn\cockpit\cockpit",
     SH / "eng/id/cockpit1P.arc", r"id\lsp\abr\cockpit\cockpit"),
    # cockpit2P is deliberately left alone: SH's 2p `Ani 0_0_2` is *smaller* than
    # Utage's (2632 vs 2736 bytes), so porting it would regress split-screen.
]

STAGING = Path(__file__).parent / "V17_STAGING"
REPORT = Path(__file__).parent / "V17_REPORT.json"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse(b):
    """-> (anim_area_start, table_start, anim_names, block_starts_abs)"""
    nodes = struct.unpack_from(">H", b, 12)[0]
    anims = struct.unpack_from(">H", b, 14)[0]
    i = b.find(b"\x00\x00\x00\x08SysRoot\x00", NODE0 + nodes * NODESZ)
    if i < 0:
        raise AssertionError("name table not found")
    table_start = i
    names = []
    for _ in range(nodes * 2 + anims):
        ln = struct.unpack_from(">I", b, i)[0]
        names.append(b[i + 4:i + 4 + ln - 1].decode("latin-1"))
        i += 4 + ln
    a0 = NODE0 + nodes * NODESZ
    starts = [m.start() - 4 for m in BOUNDARY.finditer(b, a0, table_start)]
    starts.append(table_start)
    return a0, table_start, names[nodes * 2:], starts


def clip_range(b):
    """Byte range of the `Ani 0_0_2` group (clip + its five targets)."""
    a0, tbl, anames, starts = parse(b)
    k = anames.index(CLIP)
    got = anames[k + 1:k + 1 + len(TARGETS)]
    if got != TARGETS:
        raise AssertionError(f"unexpected targets after {CLIP}: {got}")
    if k + len(TARGETS) + 1 >= len(starts):
        raise AssertionError("block boundaries do not cover the clip group")
    lo, hi = starts[k], starts[k + len(TARGETS) + 1]
    following = anames[k + len(TARGETS) + 1]
    return lo, hi, following, a0, anames


def port(utage_lsp: bytes, sh_lsp: bytes):
    ulo, uhi, unext, ua0, unames = clip_range(utage_lsp)
    slo, shi, snext, sa0, snames = clip_range(sh_lsp)
    if unext != snext:
        raise AssertionError(f"clip group is followed by {unext!r} vs {snext!r}")
    # everything before the clip group must already agree, or the splice is unsafe
    head = min(ulo - ua0, slo - sa0)
    diff = sum(1 for i in range(head)
               if utage_lsp[ua0 + i] != sh_lsp[sa0 + i])
    out = utage_lsp[:ulo] + sh_lsp[slo:shi] + utage_lsp[uhi:]
    info = {
        "clip": CLIP,
        "utage_range": [ulo - ua0, uhi - ua0], "utage_bytes": uhi - ulo,
        "sh_range": [slo - sa0, shi - sa0], "sh_bytes": shi - slo,
        "delta": (shi - slo) - (uhi - ulo),
        "preceding_bytes_compared": head, "preceding_bytes_differing": diff,
        "followed_by": unext,
    }
    return out, info


def main():
    if STAGING.exists():
        shutil.rmtree(STAGING)
    report = {"patch": "Utage V17 - SH three-line message window animation", "jobs": []}

    for utage_paths, ulsp, sh_path, slsp in JOBS:
        sh_arc = A.parse_arc(sh_path)
        hits = [e for e in sh_arc.entries if e.type_hash == LSP and e.name == slsp]
        if len(hits) != 1:
            raise AssertionError(f"{sh_path.name}: {len(hits)} matches for {slsp}")
        sh_lsp = A.unpack(hits[0])

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

            # the rewritten resource must still parse: same node/anim counts,
            # same name table, and the clip group must now be SH's bytes
            for field, off in (("nodes", 12), ("anims", 14)):
                if struct.unpack_from(">H", new, off)[0] != struct.unpack_from(">H", old, off)[0]:
                    raise AssertionError(f"{field} count changed")
            if parse(new)[2] != parse(old)[2]:
                raise AssertionError("animation name table changed")
            nlo, nhi, _, _, _ = clip_range(new)
            slo_abs, shi_abs, _, _, _ = clip_range(sh_lsp)
            if new[nlo:nhi] != sh_lsp[slo_abs:shi_abs]:
                raise AssertionError("clip group not installed")

            raw = arcbuild.build(arc, list(range(len(arc.entries))), {entry.index: new})
            rel = up.relative_to(UTAGE.parent.parent.parent.parent)
            outp = STAGING / rel
            outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_bytes(raw)

            chk = A.parse_arc(outp)
            changed = [c.index for a, c in zip(arc.entries, chk.entries)
                       if A.unpack(a) != A.unpack(c)]
            if changed != [entry.index]:
                raise AssertionError(f"unexpected changed entries: {changed}")

            info.update({"source": str(up), "lsp": ulsp, "output": str(outp),
                         "lsp_before_sha256": sha(old), "lsp_after_sha256": sha(new),
                         "lsp_before_bytes": len(old), "lsp_after_bytes": len(new)})
            report["jobs"].append(info)
            print(f"  {up.relative_to(UTAGE)}: {CLIP} {info['utage_bytes']} -> "
                  f"{info['sh_bytes']} bytes (delta {info['delta']:+d}); "
                  f"{info['preceding_bytes_differing']} differing bytes before it")

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"jobs": len(report["jobs"])}, indent=2))


if __name__ == "__main__":
    main()
