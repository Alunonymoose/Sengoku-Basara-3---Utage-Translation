#!/usr/bin/env python3
"""Find textures the English build translated in ONE archive but missed in another,
and build a basara patchset that copies the existing English art across.

Needs basara (pip install ".../project/basara"). Read-only on the game folders.

    python propagate_translated_textures.py --eng "<rom\\eng>" --jpn "<rom\\jpn>" --out C:\\propagate

The same texture is often shipped in several archives ("providers"). The
2026-09-26 visual review of every language-keyed texture found that most of the
Japanese still left in the game is exactly that: an English version exists in
one archive, while other copies of the SAME Japanese image were never updated
(stage banners in common/mission, pause move lists, Dream Chance army plates...).

Matching is by bytes, not names. A target is copied only when all of these hold:

  * target is untranslated: its ENG bytes == its own JPN bytes;
  * donor is translated from the IDENTICAL Japanese image: JPN(donor) == JPN(target);
  * donor ENG differs from its JPN (it really was edited), with the same format,
    size and mip count;
  * the donor is not legacy-damaged: `basara.xet.scan_against_reference` finds no
    blocks written by the quarantined xetenc path, and the byte-order verdict is
    not "swapped" (keeps the 2026-09-24 waza2 / result_id damage from spreading);
  * every translated donor of that image agrees on one English version, and at
    least one donor's archive kept its JPN layout (PSL members unchanged), so the
    English art fits the untouched layout the target archive still has.

Anything else is written to review.tsv instead of the patchset. Output:

    plan.json                 every group: Japanese source, donors, targets, verdict, evidence
    review.tsv                conflicts / damaged donors / layout-changed donors
    safe/patchset.toml        basara.patchset/1: one raw member copy per target
    safe/donors/<sha>.bin     the English donor members (bound by sha256)

Pairs mode (no scan): build exactly a reviewed list of copies, e.g. the
APPROVED_TEXTURE_COPIES_*.tsv produced from a plan + the visual texture review:

    python propagate_translated_textures.py --eng ... --jpn ... --out C:\\propagate2 --pairs APPROVED.tsv

Each row (member, target_arc, target_index, target_sha256, donor_arc, donor_index,
donor_sha256; optional target_member / donor_member when the same Japanese image
is stored under different names, e.g. cockpit_005 = result_011) is re-proven against the live files before it is used: both
members still have the approved bytes, both came from the SAME Japanese image,
same shape, donor not legacy-damaged. A row that fails is reported and left out.

Font pages (members under msg\\) are never copied automatically: they are glyph
atlases coupled to their archive's own TNF/CSA font tables.

Then (backup + hash-guarded install, never a ZIP):

    basara build   C:\\propagate\\safe\\patchset.toml --root "<rom\\eng>" --out C:\\propagate\\build
    basara install C:\\propagate\\build --root "<rom\\eng>" --backup-root E:\\BASARA_BACKUPS

and a cold boot of the screens listed in plan.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from basara import arc as arcmod
from basara import xet
from basara.psl import PSL_MAGIC

SKIP = re.compile(r"backup|Copy|PRE_|alrummi3", re.I)
LANG_KEY = re.compile(r"\\(jpn|eng)\\", re.I)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@dataclass
class Provider:
    arc: str
    index: int
    name: str
    eng_sha: str
    jpn_sha: str

    @property
    def translated(self) -> bool:
        return self.eng_sha != self.jpn_sha


@dataclass
class Group:
    jpn_sha: str
    name: str
    targets: list = field(default_factory=list)
    donors: list = field(default_factory=list)
    verdict: str = ""
    english_sha: str | None = None
    evidence: dict = field(default_factory=dict)


def _match(jpn_arc, e):
    """The JPN member that corresponds to ENG entry e: same index and name, else a unique name."""
    if jpn_arc is None:
        return None
    if e.index < len(jpn_arc.entries):
        j = jpn_arc.entries[e.index]
        if j.name.lower() == e.name.lower():
            return j
    hits = [j for j in jpn_arc.entries if j.name.lower() == e.name.lower()]
    return hits[0] if len(hits) == 1 else None


def _psl_changed(eng_arc, jpn_arc) -> bool:
    for e in eng_arc.entries:
        if e.magic != PSL_MAGIC:
            continue
        j = _match(jpn_arc, e)
        if j is None or j.raw != e.raw:
            return True
    return False


def scan(eng: Path, jpn: Path, all_textures: bool = False, log=print):
    providers: list[Provider] = []
    psl_changed: dict[str, bool] = {}
    n_arc = 0
    for p in sorted(eng.rglob("*.arc")):
        rel = p.relative_to(eng).as_posix()
        if SKIP.search(rel):
            continue
        jp = jpn / rel
        if not jp.exists():
            continue
        try:
            ea = arcmod.inspect(p.read_bytes())
            ja = arcmod.inspect(jp.read_bytes())
        except (arcmod.ArcError, OSError) as exc:
            log(f"skip {rel}: {exc}")
            continue
        found = False
        for e in ea.entries:
            if e.magic != xet.MAGIC or not (all_textures or LANG_KEY.search(e.name)):
                continue
            j = _match(ja, e)
            if j is None or j.magic != xet.MAGIC:
                continue
            providers.append(Provider(rel, e.index, e.name, sha(e.raw), sha(j.raw)))
            found = True
        if found:
            psl_changed[rel] = _psl_changed(ea, ja)
        n_arc += 1
        if n_arc % 1000 == 0:
            log(f"{n_arc} archives, {len(providers)} texture providers")
    return providers, psl_changed


def _load_member(root: Path, rel: str, index: int) -> bytes:
    return arcmod.inspect((root / rel).read_bytes())[index].raw


def decide(providers, psl_changed, eng: Path, jpn: Path) -> list[Group]:
    by_src: dict[str, list[Provider]] = defaultdict(list)
    for p in providers:
        by_src[p.jpn_sha].append(p)
    groups = []
    for jsha, ps in by_src.items():
        targets = [p for p in ps if not p.translated]
        donors = [p for p in ps if p.translated]
        if not targets or not donors:
            continue
        g = Group(jsha, ps[0].name, [asdict(t) for t in targets], [asdict(d) for d in donors])
        variants: dict[str, list[Provider]] = defaultdict(list)
        for d in donors:
            variants[d.eng_sha].append(d)
        valid = {}
        for esha, ds in variants.items():
            d = ds[0]
            eng_raw, jpn_raw = _load_member(eng, d.arc, d.index), _load_member(jpn, d.arc, d.index)
            ev = {"donors": [f"{x.arc}#{x.index}" for x in ds]}
            try:
                a, b = xet.xet_info(eng_raw), xet.xet_info(jpn_raw)
                ev["shape"] = f"{a.width}x{a.height} 0x{a.format_code:02X} mips {a.mip_count}"
                ev["same_shape"] = (a.width, a.height, a.format_code, a.mip_count) == (b.width, b.height, b.format_code, b.mip_count)
                bo = xet.byte_order_evidence(eng_raw)
                ev["byte_order"] = bo.get("verdict", "n/a")
                sc = xet.scan_against_reference(eng_raw, jpn_raw)
                ev["legacy_damage"] = bool(sc.get("suspect_legacy_encoding"))
                ev["blocks_changed"] = sc.get("blocks_changed")
            except xet.XetError as exc:
                ev["error"] = str(exc)
            ev["layout_kept"] = any(not psl_changed.get(x.arc, True) for x in ds)
            g.evidence[esha] = ev
            if ev.get("same_shape") and ev.get("byte_order") != "swapped" and not ev.get("legacy_damage") and "error" not in ev:
                valid[esha] = ev
        if g.name.lower().startswith("msg\\"):
            g.verdict = "REVIEW_FONT_PAGE"            # glyph atlas: coupled to the archive's TNF/CSA
        elif len(valid) == 1:
            esha, ev = next(iter(valid.items()))
            g.english_sha = esha
            g.verdict = "SAFE" if ev["layout_kept"] else "REVIEW_LAYOUT_CHANGED_IN_DONOR"
        elif len(valid) > 1:
            g.verdict = "REVIEW_CONFLICTING_ENGLISH_VERSIONS"
        else:
            g.verdict = "REPAIR_DONOR_FIRST"
        groups.append(g)
    groups.sort(key=lambda g: (g.verdict != "SAFE", g.name))
    return groups


def write_outputs(groups, eng: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps([asdict(g) for g in groups], indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out / "review.tsv", "w", encoding="utf-8") as f:
        f.write("verdict\tmember\ttargets\tenglish_versions\n")
        for g in groups:
            if g.verdict != "SAFE":
                tg = ", ".join(f"{t['arc']}#{t['index']}" for t in g.targets)
                vs = " | ".join(f"{k[:12]}: {v}" for k, v in g.evidence.items())
                f.write(f"{g.verdict}\t{g.name}\t{tg}\t{vs}\n")
    jobs = []
    for g in groups:
        if g.verdict != "SAFE":
            continue
        donor = g.evidence[g.english_sha]["donors"][0]
        blob = _load_member(eng, donor.rsplit("#", 1)[0], int(donor.rsplit("#", 1)[1]))
        assert sha(blob) == g.english_sha
        jobs += [(t["arc"], t["index"], t["name"], blob, donor) for t in g.targets]
    per_arc = _write_patchset(jobs, eng, out / "safe")
    counts: dict[str, int] = defaultdict(int)
    for g in groups:
        counts[g.verdict] += 1
    return {"groups": dict(counts), "safe_targets": sum(len(v) for v in per_arc.values()),
            "safe_archives": len(per_arc)}


def _write_patchset(jobs, eng: Path, out: Path) -> dict:
    """jobs: (target_arc, target_index, name, donor_bytes, donor_label) -> patchset.toml + donors/."""
    donors_dir = out / "donors"
    donors_dir.mkdir(parents=True, exist_ok=True)
    per_arc: dict[str, list] = defaultdict(list)
    for arc, idx, name, blob, label in jobs:
        h = sha(blob)
        (donors_dir / f"{h[:16]}.bin").write_bytes(blob)
        per_arc[arc].append((idx, name, h, label))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    lines = ['schema = "basara.patchset/1"', f'id = "propagate-translated-textures-{stamp}"', ""]
    for rel in sorted(per_arc):
        lines += ["[[archive]]", f'path = "{rel}"', f'sha256 = "{sha((eng / rel).read_bytes())}"', ""]
        for idx, name, h, label in sorted(per_arc[rel]):
            lines += [f"  # {name}  <- {label}", "  [[archive.member]]", f"  member = {idx}",
                      f'  source = "donors/{h[:16]}.bin"', f'  source_sha256 = "{h}"', ""]
    (out / "patchset.toml").write_text("\n".join(lines), encoding="utf-8")
    return per_arc


def build_pairs(pairs_tsv: Path, eng: Path, jpn: Path, out: Path, log=print) -> dict:
    """Re-prove every approved (target, donor) row against the live files and emit a patchset."""
    lines = [ln for ln in Path(pairs_tsv).read_text(encoding="utf-8").splitlines() if ln.strip()]
    head = lines[0].split("\t")
    rows = [dict(zip(head, ln.split("\t"), strict=True)) for ln in lines[1:]]
    cache: dict[tuple, arcmod.Archive | None] = {}

    def archive(root: Path, rel: str):
        key = (str(root), rel)
        if key not in cache:
            p = root / rel
            cache[key] = arcmod.inspect(p.read_bytes()) if p.exists() else None
        return cache[key]

    def member(root, rel, idx, name):
        a = archive(root, rel)
        if a is None or idx >= len(a.entries):
            return None
        e = a.entries[idx]
        return e if e.name.lower() == name.lower() else None

    def jpn_member(rel, idx, name):
        """The JPN counterpart: same index and name, else a unique name (as in scan())."""
        e = member(jpn, rel, idx, name)
        if e is not None:
            return e
        a = archive(jpn, rel)
        hits = [x for x in (a.entries if a else ()) if x.name.lower() == name.lower()]
        return hits[0] if len(hits) == 1 else None

    jobs, report = [], []
    for row in rows:
        t_arc, d_arc = row["target_arc"], row["donor_arc"]
        name = row.get("target_member") or row["member"]
        d_name = row.get("donor_member") or row["member"]
        t_idx, d_idx = int(row["target_index"]), int(row["donor_index"])
        label = f"{d_arc}#{d_idx}"
        problems = []
        te, de = member(eng, t_arc, t_idx, name), member(eng, d_arc, d_idx, d_name)
        tj, dj = jpn_member(t_arc, t_idx, name), jpn_member(d_arc, d_idx, d_name)
        if te is None or de is None:
            problems.append("member missing or renamed in rom/eng")
        elif sha(te.raw) != row["target_sha256"]:
            problems.append("target changed since approval")
        elif sha(de.raw) != row["donor_sha256"]:
            problems.append("donor changed since approval")
        if not problems:
            if tj is None or dj is None or sha(tj.raw) != sha(dj.raw):
                problems.append("target and donor do not come from the same Japanese image")
            else:
                a, b = xet.xet_info(te.raw), xet.xet_info(de.raw)
                if (a.width, a.height, a.format_code, a.mip_count) != (b.width, b.height, b.format_code, b.mip_count):
                    problems.append("shape differs")
                if xet.byte_order_evidence(de.raw).get("verdict") == "swapped" or \
                        xet.scan_against_reference(de.raw, dj.raw).get("suspect_legacy_encoding"):
                    problems.append("donor shows legacy-writer damage")
        report.append({"member": name, "target": f"{t_arc}#{t_idx}", "donor": label, "ok": not problems,
                       "problems": problems})
        if problems:
            log(f"LEFT OUT {name} {t_arc}#{t_idx}: {'; '.join(problems)}")
            continue
        jobs.append((t_arc, t_idx, name, de.raw, label))
    per_arc = _write_patchset(jobs, eng, out)
    (out / "pairs_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"approved_rows": len(rows), "copies": len(jobs), "archives": len(per_arc),
            "left_out": len(rows) - len(jobs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--jpn", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--all-textures", action="store_true",
                    help="consider every XET, not only names with a \\jpn\\ or \\eng\\ folder")
    ap.add_argument("--pairs", help="build exactly these reviewed copies (TSV) instead of scanning")
    a = ap.parse_args()
    eng, jpn, out = Path(a.eng), Path(a.jpn), Path(a.out)
    if out.resolve() == eng.resolve() or eng.resolve() in out.resolve().parents:
        print("--out must be outside the live rom/eng tree", file=sys.stderr)
        return 2
    if a.pairs:
        summary = build_pairs(Path(a.pairs), eng, jpn, out, log=lambda m: print(m, flush=True))
        print(f"done: {summary}\n  patchset: {out / 'patchset.toml'}\n  report:   {out / 'pairs_report.json'}")
        return 0
    providers, psl = scan(eng, jpn, a.all_textures, log=lambda m: print(m, flush=True))
    groups = decide(providers, psl, eng, jpn)
    summary = write_outputs(groups, eng, out)
    print(f"done: {len(providers)} providers; {summary}")
    print(f"  patchset: {out / 'safe' / 'patchset.toml'}\n  review:   {out / 'review.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
