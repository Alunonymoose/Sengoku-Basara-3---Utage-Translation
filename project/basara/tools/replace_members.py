#!/usr/bin/env python3
"""Turn a reviewed set of replacement member files into a basara patchset, re-proven on the live files.

Needs basara (pip install ".../project/basara"). Read-only on the game folders.

    python replace_members.py --eng "<rom\\eng>" --list REPAIR.tsv --files <folder> --out C:\\repair_build_in

For repairs computed off-machine (e.g. the 2026-09-26 waza2 neutral-chroma fix): the exact
replacement bytes were built from the live member, shown on a before/after board and approved.
Each TSV row (arc, index, member, before_sha256, file, after_sha256) is used only if
  * the live member at that index has that name and still has before_sha256
    (the bytes the repair was computed from);
  * the file has after_sha256 (the bytes that were approved);
  * for XET: same size, format and mip count.
Anything else is reported and left out. Output: patchset.toml + donors/ + replace_report.json,
then the usual `basara build` -> `basara install` (verified backup, hash-guarded write).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from basara import arc as arcmod
from basara import xet


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build(list_tsv: Path, files: Path, eng: Path, out: Path, log=print) -> dict:
    lines = [ln for ln in Path(list_tsv).read_text(encoding="utf-8").splitlines() if ln.strip()]
    head = lines[0].split("\t")
    rows = [dict(zip(head, ln.split("\t"), strict=True)) for ln in lines[1:]]
    cache: dict[str, arcmod.Archive | None] = {}
    per_arc: dict[str, list] = defaultdict(list)
    report = []
    donors = out / "donors"
    donors.mkdir(parents=True, exist_ok=True)
    for row in rows:
        rel, idx, name = row["arc"], int(row["index"]), row["member"]
        problems = []
        if rel not in cache:
            p = eng / rel
            cache[rel] = arcmod.inspect(p.read_bytes()) if p.exists() else None
        a = cache[rel]
        e = a.entries[idx] if a is not None and idx < len(a.entries) else None
        f = files / row["file"]
        new = f.read_bytes() if f.exists() else None
        if e is None or e.name.lower() != name.lower():
            problems.append("member missing or renamed in rom/eng")
        elif sha(e.raw) != row["before_sha256"]:
            problems.append("live member changed since the repair was computed")
        if new is None:
            problems.append("replacement file missing")
        elif sha(new) != row["after_sha256"]:
            problems.append("replacement file is not the approved bytes")
        if not problems and e.magic == xet.MAGIC:
            i, j = xet.xet_info(e.raw), xet.xet_info(new)
            if (i.width, i.height, i.format_code, i.mip_count) != (j.width, j.height, j.format_code, j.mip_count):
                problems.append("shape differs")
        report.append({"target": f"{rel}#{idx}", "member": name, "ok": not problems, "problems": problems})
        if problems:
            log(f"LEFT OUT {name} {rel}#{idx}: {'; '.join(problems)}")
            continue
        (donors / f"{row['after_sha256'][:16]}.bin").write_bytes(new)
        per_arc[rel].append((idx, name, row["after_sha256"]))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    text = ['schema = "basara.patchset/1"', f'id = "{Path(list_tsv).stem.lower()}-{stamp}"', ""]
    for rel in sorted(per_arc):
        text += ["[[archive]]", f'path = "{rel}"', f'sha256 = "{sha((eng / rel).read_bytes())}"', ""]
        for idx, name, h in sorted(per_arc[rel]):
            text += [f"  # {name}", "  [[archive.member]]", f"  member = {idx}",
                     f'  source = "donors/{h[:16]}.bin"', f'  source_sha256 = "{h}"', ""]
    (out / "patchset.toml").write_text("\n".join(text), encoding="utf-8")
    (out / "replace_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    n = sum(len(v) for v in per_arc.values())
    return {"rows": len(rows), "replacements": n, "archives": len(per_arc), "left_out": len(rows) - n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--files", required=True, help="folder holding the approved replacement files")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    eng, out = Path(a.eng), Path(a.out)
    if out.resolve() == eng.resolve() or eng.resolve() in out.resolve().parents:
        print("--out must be outside the live rom/eng tree", file=sys.stderr)
        return 2
    res = build(Path(a.list), Path(a.files), eng, out, log=lambda m: print(m, flush=True))
    print(f"done: {res}\n  patchset: {out / 'patchset.toml'}\n  report:   {out / 'replace_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
