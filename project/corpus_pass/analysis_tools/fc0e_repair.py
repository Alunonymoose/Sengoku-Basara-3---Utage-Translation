"""Repair FC0E damage: restore JPN FC0E args, drop injected words. Proves the fix offline and
emits one basara patchset per archive (build/install happen on the laptop against live bytes)."""
import json, collections, sys
from pathlib import Path
from basara.msg import Gsm, Fim, apply, check, detect_grammar, GRAMMARS, MsgError
from basara.font import Csa
from basara.markup import decode, encode
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
m = json.load(open("MANIFEST.json"))
files = collections.defaultdict(dict)
for f in m["files"]:
    files[f["tree"]][(f["arc"], f["name"], f["kind"])] = f
csa = Csa.parse(Path(next(f["path"] for f in m["files"] if f["tree"] == "utage_eng" and f["kind"] == "csa")).read_bytes())

def repaired(ew, jw):
    """ENG words with every FC0E triple replaced by the JPN triple and injected words removed.
    None if FC0E occurrences don't line up with the JPN record."""
    je = [(jw[i + 1], jw[i + 2]) for i, w in enumerate(jw) if w == 0xFC0E and i + 2 < len(jw)]
    out, i, n = [], 0, 0
    while i < len(ew):
        w = ew[i]
        if w == 0xFC0E and i + 2 < len(ew):
            if n >= len(je): return None
            out += [0xFC0E, *je[n]]; n += 1; i += 3
            while i < len(ew) and ew[i] < 0xF000: i += 1   # injected plain words
            continue
        out.append(w); i += 1
    return out if n == len(je) else None

summary = {"archives": 0, "tables": 0, "records": 0, "skipped_misaligned": 0, "contract_ok_tables": 0}
for (arc, name, kind), f in sorted(files["utage_eng"].items()):
    if kind != "gsm" or "BACKUP" in arc: continue
    jf = files["utage_jpn"].get((arc, name, "gsm")); ff = files["utage_eng"].get((arc, name, "fim"))
    if not jf or not ff: continue
    ge = Gsm.parse(Path(f["path"]).read_bytes()); gj = Gsm.parse(Path(jf["path"]).read_bytes())
    changes = {}
    for r in range(min(len(ge), len(gj))):
        ew = ge.words(r)
        if 0xFC0E not in ew: continue
        new = repaired(list(ew), list(gj.words(r)))
        if new is None: summary["skipped_misaligned"] += 1; continue
        if new != list(ew): changes[r] = new
    if not changes: continue
    fim = Fim.parse(Path(ff["path"]).read_bytes())
    gname = detect_grammar(ge, fim)
    ng = ge.with_records(changes); nf = apply(ng, fim, GRAMMARS[gname])
    rep = check(ng, nf, gname)
    assert rep.ok, (arc, name, rep.violations[:2], rep.errors[:1])
    # nothing but the FC0E records changed; FIM only col0/col1-high moved
    assert all(ng.words(r) == ge.words(r) for r in range(len(ge)) if r not in changes)
    assert all(a[2:] == b[2:] and (a[1] & 0xFFFF) == (b[1] & 0xFFFF) for a, b in zip(fim.secondary, nf.secondary))
    summary["tables"] += 1; summary["records"] += len(changes); summary["contract_ok_tables"] += 1
    # patchset text ops (markup round-trips exactly under this table's grammar)
    ops = []
    for r, new in sorted(changes.items()):
        cur = decode(ge.words(r), csa, GRAMMARS[gname]); fixed = decode(new, csa, GRAMMARS[gname])
        assert encode(fixed, csa, GRAMMARS[gname]) == new and encode(cur, csa, GRAMMARS[gname]) == list(ge.words(r))
        ops.append((r, cur, fixed))
    p = OUT / (arc.replace("/", "__") + ".toml")
    head = not p.exists()
    with open(p, "a", encoding="utf-8") as fh:
        if head:
            summary["archives"] += 1
            fh.write(f'schema = "basara.patchset/1"\nid = "fc0e-repair-{Path(arc).stem}"\n\n[[archive]]\npath = {json.dumps(arc)}\nsha256 = "{f["arc_sha256"]}"\n')
        for r, cur, fixed in ops:
            fh.write(f'\n  [[archive.text]]\n  table = {json.dumps(name)}\n  record = {r}\n  expect = {json.dumps(cur, ensure_ascii=False)}\n'
                     f'  text = {json.dumps(fixed, ensure_ascii=False)}\n  allow_structure_change = true   # restores the JPN FC0E arguments\n')
print(json.dumps(summary, indent=1))
