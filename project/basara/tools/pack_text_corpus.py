#!/usr/bin/env python3
"""Pack ONLY the text tables of Utage + Samurai Heroes into small upload parts.

Standard library only -- no pip install needed. Read-only on the game folders.

    python pack_text_corpus.py --out C:\\corpus ^
        --tree utage_eng="E:\\Utage Patching New\\PS3_GAME\\USRDIR\\nativePS3\\rom\\eng" ^
        --tree utage_jpn="E:\\Utage Patching New\\PS3_GAME\\USRDIR\\nativePS3\\rom\\jpn" ^
        --tree sh="E:\\SAMURAI HEROES\\PS3_GAME\\USRDIR\\nativePS3\\rom"

For every *.arc under each tree it extracts the GSM (text), FIM (dialogue
timing) and CSA (character map) members -- nothing else -- and writes
corpus_partNN.zip files of at most --max-mb (default 29) each, plus
MANIFEST.json (source path, member index/name, sha256 of every extracted
member and of every source ARC). Identical CSA maps are stored once.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

KEEP = {b"\x00GSM": "gsm", b"\x00FIM": "fim", b"\x00CSA": "csa"}


def members(data: bytes):
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
        if raw is None:
            continue
        kind = KEEP.get(raw[:4])
        if kind:
            yield i, rec[:64].split(b"\0", 1)[0].decode("utf-8", "replace"), kind, raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", action="append", required=True, help="label=path (repeatable)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-mb", type=float, default=29.0)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    limit = int(a.max_mb * 1024 * 1024)
    manifest = {"tool": "pack_text_corpus 1", "trees": {}, "files": []}
    part, zf, seen_csa = 0, None, {}

    def open_part():
        nonlocal part, zf
        if zf:
            zf.close()
        part += 1
        zf = zipfile.ZipFile(out / f"corpus_part{part:02}.zip", "w", zipfile.ZIP_LZMA)

    open_part()
    n_arc = 0
    for spec in a.tree:
        label, _, root = spec.partition("=")
        root = Path(root)
        if not root.is_dir():
            print(f"!! not a folder: {root}", file=sys.stderr)
            return 2
        manifest["trees"][label] = str(root)
        for arc in sorted(root.rglob("*.arc")):
            try:
                data = arc.read_bytes()
            except OSError as exc:
                print(f"skip {arc}: {exc}", file=sys.stderr)
                continue
            rel = arc.relative_to(root).as_posix()
            found = list(members(data))
            if not found:
                continue
            n_arc += 1
            for idx, name, kind, raw in found:
                h = hashlib.sha256(raw).hexdigest()
                entry = {"tree": label, "arc": rel, "arc_sha256": hashlib.sha256(data).hexdigest(),
                         "index": idx, "name": name, "kind": kind, "sha256": h}
                if kind == "csa" and h in seen_csa:
                    entry["path"] = seen_csa[h]
                else:
                    path = f"{label}/{rel}/{idx:04}.{kind}"
                    if (out / f"corpus_part{part:02}.zip").stat().st_size > limit - len(raw) - 4096:
                        open_part()
                    zf.writestr(path, raw)
                    entry["path"], entry["part"] = path, part
                    if kind == "csa":
                        seen_csa[h] = path
                manifest["files"].append(entry)
            if n_arc % 200 == 0:
                print(f"{n_arc} archives...", flush=True)
    zf.writestr("MANIFEST.json", json.dumps(manifest, indent=1, ensure_ascii=False))
    zf.close()
    print(f"done: {n_arc} archives with text, {len(manifest['files'])} tables, {part} part(s) in {out}")
    for p in sorted(out.glob("corpus_part*.zip")):
        print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
