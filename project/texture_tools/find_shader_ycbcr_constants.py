#!/usr/bin/env python3
"""Find the 0x2A YCbCr decode constants inside the game's own compiled shaders.

Standard library only. Read-only.

    python find_shader_ycbcr_constants.py "E:\\Utage Patching New\\PS3_GAME\\USRDIR\\nativePS3"

Scans every file under the given folders (and every member of any ARC among
them) for the BT.601 YCbCr->RGB constants as the RSX stores fragment-program
constants: IEEE-754 big-endian floats with the two 16-bit halves swapped.
Plain big- and little-endian encodings are searched too, for completeness.

A "set" is all five decode constants (offset, 1.402, 0.34414, 0.71414, 1.772)
within --window bytes of each other, i.e. one compiled program's constant
block. The offset is reported for both candidates, -123/255 (what the project
decodes with) and -128/255 (textbook), so the tool can falsify the project's
rule as easily as confirm it.

First run 2026-09-26 on the user's sa.zip (nativePS3/sa, sc, system):
sc/PS3/Basara/package.spkg 16 sets, sc/PS3/package.spkg 1 set, all -123/255;
no -128/255 anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

CONSTANTS = {
    "offset_123": -123 / 255,       # stored as -0.482353 (source literal rounded to 6 places)
    "offset_128": -128 / 255,
    "offset_half": -0.5,
    "r_cr": 1.402,
    "g_cb": 0.34414,
    "g_cr": 0.71414,
    "b_cb": 1.772,
}
DECODE = ("r_cr", "g_cb", "g_cr", "b_cb")


OFFSETS = ("offset_123", "offset_128", "offset_half")
TOL = 2e-6                          # shader source literals are rounded (e.g. -0.482353 for -123/255)


def _read(enc: str, data: bytes, at: int) -> float:
    w = data[at:at + 4]
    if enc == "rsx":                # RSX fragment constants: big-endian float, 16-bit halves swapped
        w = w[2:4] + w[0:2]
    return struct.unpack("<f" if enc == "le" else ">f", w)[0]


def positions(data: bytes, enc: str, x: float) -> list[int]:
    """Start offsets of every stored float within TOL of x (found via its high half-word)."""
    out = set()
    for probe in (x - TOL, x + TOL):
        be = struct.pack(">f", probe)
        hi, rel = {"rsx": (be[0:2], 2), "be": (be[0:2], 0), "le": (be[1::-1], 2)}[enc]
        i = data.find(hi)
        while i >= 0:
            at = i - rel
            if at >= 0 and at + 4 <= len(data) and abs(_read(enc, data, at) - x) <= TOL:
                out.add(at)
            i = data.find(hi, i + 1)
    return sorted(out)


def arc_members(data: bytes):
    if data[:4] != b"\x00CRA":
        return
    _ver, count = struct.unpack_from(">HH", data, 4)
    for i in range(count):
        rec = data[8 + i * 80: 8 + (i + 1) * 80]
        if len(rec) < 80:
            return
        _th, size, packed, off = struct.unpack_from(">IIII", rec, 64)
        stored = data[off:off + size]
        try:
            raw = zlib.decompress(stored)
        except zlib.error:
            raw = stored if len(stored) == packed >> 3 else None
        if raw is not None:
            yield i, rec[:64].split(b"\0", 1)[0].decode("utf-8", "replace"), raw


def scan(label: str, data: bytes, window: int) -> dict | None:
    found = {}
    for enc in ("rsx", "be", "le"):
        pos = {k: positions(data, enc, v) for k, v in CONSTANTS.items()}
        if not any(pos[k] for k in DECODE):          # a lone 0.5 is everywhere; only report decode matrices
            continue
        sets = {}
        for off_key in OFFSETS:
            n = 0
            for p in pos[off_key]:
                if all(any(abs(q - p) <= window for q in pos[k]) for k in DECODE):
                    n += 1
            sets[off_key] = n
        found[enc] = {"counts": {k: len(v) for k, v in pos.items()}, "sets": sets}
    if not found:
        return None
    return {"file": label, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "hits": found}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--window", type=int, default=512, help="max bytes between constants of one set")
    a = ap.parse_args()
    total = dict.fromkeys(OFFSETS, 0)
    for root in map(Path, a.roots):
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in files:
            try:
                data = p.read_bytes()
            except OSError as exc:
                print(f"skip {p}: {exc}", file=sys.stderr)
                continue
            blobs = [(str(p), data)] + [(f"{p}#{i} {name}", raw) for i, name, raw in arc_members(data)]
            for label, blob in blobs:
                r = scan(label, blob, a.window)
                if r is None:
                    continue
                print(f"{r['file']}  size {r['size']}  sha256 {r['sha256'][:16]}")
                for enc, h in r["hits"].items():
                    print(f"   {enc:3}  sets with offset -123/255: {h['sets']['offset_123']:3}  -128/255: {h['sets']['offset_128']:3}"
                          f"  -0.5: {h['sets']['offset_half']:3}  counts {h['counts']}")
                if "#" not in label:                       # count each program once (raw file, not its ARC copy)
                    for k in total:
                        total[k] += r["hits"].get("rsx", {}).get("sets", {}).get(k, 0)
    print(f"TOTAL rsx sets in plain files: -123/255 = {total['offset_123']}, -128/255 = {total['offset_128']},"
          f" -0.5 = {total['offset_half']}")
    textbook = total["offset_128"] + total["offset_half"]
    verdict = ("CONFIRMS neutral chroma 123" if total["offset_123"] and not textbook
               else "CONTRADICTS neutral chroma 123 -- stop and re-check the codec" if textbook
               else "no decode constants found")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
