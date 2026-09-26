#!/usr/bin/env python3
"""Pack specific archive members (live ENG + their JPN counterparts) into one small zip for review.

Needs basara (pip install ".../project/basara"). Read-only on the game folders.

    python pack_members.py --eng "<rom\\eng>" --jpn "<rom\\jpn>" --list REPAIR_INPUTS.txt --out C:\\review\\members.zip

--list: one "arc#index" per line (e.g. "select/c_common.arc#1"); "# ..." comments allowed.
A line "layout arc" (e.g. "layout result_id.arc") adds every PSL layout member of that archive.

For each member the zip holds eng/<arc>/<index>.<ext> and, when rom/jpn has the same member
(same index and name, else a unique name), jpn/<arc>/<index>.<ext>. MANIFEST.json lists names,
sizes and sha256 of everything, plus each source archive's sha256, so the result can be tied
to exact live bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from basara import arc as arcmod
from basara.psl import PSL_MAGIC

EXT = {b"\x00XET": "tex", PSL_MAGIC: "psl", b"\x00GSM": "gsm", b"\x00FIM": "fim", b"\x00TNF": "tnf", b"\x00CSA": "csa"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _counterpart(ja, e):
    if ja is None:
        return None
    if e.index < len(ja.entries) and ja.entries[e.index].name.lower() == e.name.lower():
        return ja.entries[e.index]
    hits = [j for j in ja.entries if j.name.lower() == e.name.lower()]
    return hits[0] if len(hits) == 1 else None


def parse_list(text: str) -> tuple[list[tuple[str, int]], list[str]]:
    members, layouts = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()           # inline comment: "arc#1  # note"
        if line.startswith("layout "):
            layouts.append(line.split(None, 1)[1].strip())
            continue
        a, _, i = line.rpartition("#")
        members.append((a.strip(), int(i)))
    return members, layouts


def pack(eng: Path, jpn: Path, members, layouts, out: Path, log=print) -> dict:
    cache: dict[tuple, object] = {}

    def load(root: Path, rel: str):
        key = (str(root), rel)
        if key not in cache:
            p = root / rel
            data = p.read_bytes() if p.exists() else None
            cache[key] = (data, arcmod.inspect(data) if data else None)
        return cache[key]

    wanted: list[tuple[str, int]] = list(members)
    for rel in layouts:
        _, ea = load(eng, rel)
        if ea is None:
            log(f"missing {rel}")
            continue
        wanted += [(rel, e.index) for e in ea.entries if e.magic == PSL_MAGIC]
    manifest = {"tool": "pack_members 1", "archives": {}, "members": []}
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, idx in dict.fromkeys(wanted):
            edata, ea = load(eng, rel)
            jdata, ja = load(jpn, rel)
            if ea is None or idx >= len(ea.entries):
                log(f"missing {rel}#{idx}")
                continue
            manifest["archives"][rel] = {"eng_sha256": sha(edata), "jpn_sha256": sha(jdata) if jdata else None}
            e = ea.entries[idx]
            j = _counterpart(ja, e)
            ext = EXT.get(e.magic, "bin")
            rec = {"arc": rel, "index": idx, "name": e.name, "eng_sha256": sha(e.raw), "eng_size": len(e.raw)}
            zf.writestr(f"eng/{rel}/{idx:04}.{ext}", e.raw)
            if j is not None:
                zf.writestr(f"jpn/{rel}/{idx:04}.{ext}", j.raw)
                rec.update(jpn_index=j.index, jpn_sha256=sha(j.raw), same_as_jpn=j.raw == e.raw)
            manifest["members"].append(rec)
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=1, ensure_ascii=False))
    return {"members": len(manifest["members"]), "zip": str(out), "mb": round(out.stat().st_size / 1e6, 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--jpn", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    members, layouts = parse_list(Path(a.list).read_text(encoding="utf-8"))
    res = pack(Path(a.eng), Path(a.jpn), members, layouts, Path(a.out), log=lambda m: print(m, file=sys.stderr))
    print(f"done: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
