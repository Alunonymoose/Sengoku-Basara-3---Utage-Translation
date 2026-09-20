#!/usr/bin/env python3
"""
UTAGE - FIM FORMAT CONTRACT ROLLBACK

Restores every col0 / col1-high16 value that FIM_CONTRACT_REPAIR.py changed,
using FIM_CONTRACT_REPAIR_UNDO.json. Nothing else is touched, so this returns
rom\eng\id to its exact pre-repair bytes in those fields.
"""

import json, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from FIM_CONTRACT_REPAIR import (ROOT, ENG, WORK, parse_arc, unpack, rebuild,
                                 parse_arc_bytes)

def rollback_one(path, undo):
    data, endian, version, entries = parse_arc(path)
    raws = dict((e.index, unpack(e)) for e in entries)
    by = {}
    for e in entries: by.setdefault((e.name, raws[e.index][:4]), e.index)
    repl = {}; n = 0
    for name in undo:
        fi = by.get((name, b"\0FIM"))
        if fi is None:
            raise ValueError("no FIM for resource %s" % name)
        fraw = raws[fi]
        n1 = struct.unpack_from(">I", fraw, 8)[0]
        base = 32 + n1*20
        out = bytearray(fraw)
        for j, c0, c1hi in undo[name]:
            o = base + j*44
            struct.pack_into(">I", out, o, c0)
            struct.pack_into(">H", out, o+4, c1hi)
            n += 1
        repl[fi] = bytes(out)
    if not repl: return 0
    newdata = rebuild(data, endian, entries, repl)
    _, _, _, ents2 = parse_arc_bytes(newdata)
    assert len(ents2) == len(entries), "entry count changed"
    nraws = dict((e.index, unpack(e)) for e in ents2)
    for a, b in zip(entries, ents2):
        assert a.name == b.name and a.type_hash == b.type_hash and a.flags == b.flags
        if a.index not in repl:
            assert nraws[b.index] == raws[a.index], "untouched entry %d changed" % a.index
    path.write_bytes(newdata)
    return n

def main():
    up = WORK/"FIM_CONTRACT_REPAIR_UNDO.json"
    if not up.exists():
        print("!! no undo record at %s" % up); return 2
    undo_all = json.loads(up.read_text(encoding="utf-8"))
    print("rolling back %d archives" % len(undo_all))
    total = 0; done = 0; errors = []
    for k, fname in enumerate(sorted(undo_all), 1):
        p = ENG/fname
        if not p.exists():
            errors.append((fname, "missing")); continue
        try:
            total += rollback_one(p, undo_all[fname]); done += 1
        except Exception as ex:
            errors.append((fname, "%s: %s" % (type(ex).__name__, ex)))
            print("  ERROR %s: %s" % (fname, ex))
        if k % 200 == 0: print("  [%d/%d]" % (k, len(undo_all)))
    print("\nrestored %d format records across %d archives; errors=%d" % (total, done, len(errors)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
