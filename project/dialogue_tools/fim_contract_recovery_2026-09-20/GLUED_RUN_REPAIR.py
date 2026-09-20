#!/usr/bin/env python3
"""
UTAGE - GLUED STYLED RUN REPAIR

DEFECT
------
A styled run (FF92 .. FF91) that begins flush against the preceding text,
with no separating space, renders as one fused word:

    "The Nanbu Night March of the Dead" + "effect has ended"
        -> "The Nanbu Night March of the Deadeffect has ended"

Japanese needed no space because the particle carried the join. English
does. This inserts a single space glyph (0x0000) immediately before the
FF92 that opens the run.

SAFETY
------
* Archives whose font is still Japanese (>= 600 glyphs) are SKIPPED -
  their text is untranslated and decoding it as Latin produces nonsense.
* Inserting a text glyph lengthens the record, so the GSM pool and
  descriptor table are rebuilt, and FIM col0 / col1-high16 are then
  recomputed from the new text by the same contract used by
  FIM_CONTRACT_REPAIR. Speech count, FIM primary table and secondary
  col8 (voice links) are asserted unchanged.
* Every archive is rebuilt and fully verified IN MEMORY before writing.
* The original file is copied to _GLUED_RUN_BACKUP\ before it is written.
"""

import json, shutil, struct, sys, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from FIM_CONTRACT_REPAIR import (ROOT, ENG, ARGC, parse_arc, unpack, rebuild,
                                 parse_arc_bytes, gsm_records, tokens, desired)

WORK   = ROOT / "_FIM_CONTRACT_REPAIR"
BACKUP = ROOT / "_GLUED_RUN_BACKUP"

SPACE = 0x0000
# characters that make a join legitimate (no space wanted)
OK_PREV  = " \n"
OK_FIRST = " ,.!?:;'-\n)]}"

def dec(g):
    c = g + 32 if g < 0x06 else g + 33
    return chr(c) if 32 <= c <= 126 else None

def find_glued(rec):
    """token offsets of FF92 whose run is glued to the preceding word"""
    hits = []; prev = None; pend = False
    for o, v, vs in tokens(rec):
        if v in (0xFFFE, 0xFFFD): prev = None; pend = False; continue
        if v == 0xFF92: pend = o; continue
        if v == 0xFF91: pend = False; continue
        if v >= 0x8000: prev = None; pend = False; continue
        ch = dec(v)
        if ch is None: continue
        if pend is not False:
            if prev is not None and prev not in OK_PREV and ch not in OK_FIRST:
                hits.append(pend)
            pend = False
        prev = ch
    return hits

def build_gsm(template, records):
    """rebuild a \0GSM blob from a list of records (pool is strictly sequential)"""
    out = bytearray(template[:16])
    pool = []; table = bytearray()
    for r in records:
        table += struct.pack(">II", len(pool), len(r))
        pool.extend(r)
    struct.pack_into(">I", out, 8, len(pool))
    struct.pack_into(">I", out, 12, len(records))
    out += table
    for w in pool: out += struct.pack(">H", w)
    assert len(out) == 16 + len(records)*8 + len(pool)*2
    return bytes(out)

def font_glyphs(entries, raws):
    for e in entries:
        if raws[e.index][:4] == b"\0TNF":
            return struct.unpack_from(">I", raws[e.index], 8)[0]
    return None

def speech_counts(rec):
    ts = tokens(rec)
    return 1 + sum(1 for o, v, vs in ts
                   if v == 0xFFFD and o + len(vs) < len(rec) - 1)

def process(path):
    data0, endian, version, entries = parse_arc(path)
    raws = dict((e.index, unpack(e)) for e in entries)

    gc = font_glyphs(entries, raws)
    if gc is None or gc >= 600:
        return "skipped_untranslated", 0, None

    by = {}
    for e in entries: by.setdefault((e.name, raws[e.index][:4]), e.index)

    repl = {}; fixed = 0; log = []
    for e in entries:
        if raws[e.index][:4] != b"\0GSM": continue
        fi = by.get((e.name, b"\0FIM"))
        if fi is None: continue
        recs = gsm_records(raws[e.index])
        changed = False
        for ri, r in enumerate(recs):
            try: hits = find_glued(r)
            except Exception: break
            if not hits: continue
            before = speech_counts(r)
            new = list(r)
            for o in sorted(hits, reverse=True):
                new.insert(o, SPACE)
            assert speech_counts(new) == before, "speech count changed"
            recs[ri] = new; changed = True; fixed += len(hits)
            log.append({"res": e.name, "rec": ri, "inserted": len(hits)})
        if changed:
            repl[e.index] = build_gsm(raws[e.index], recs)

    if not repl:
        return "clean", 0, None

    # --- recompute FIM col0 / col1-high for every pair, from the NEW text ---
    for e in entries:
        if raws[e.index][:4] != b"\0GSM": continue
        fi = by.get((e.name, b"\0FIM"))
        if fi is None: continue
        g = repl.get(e.index, raws[e.index])
        f = repl.get(fi, raws[fi])
        want, base = desired(g, f)
        out = bytearray(f)
        for j in want:
            lines, glyphs, s = want[j]
            o = base + j*44
            struct.pack_into(">I", out, o, (lines << 16) | glyphs)
            struct.pack_into(">H", out, o+4, s)
        repl[fi] = bytes(out)

    data = rebuild(data0, endian, entries, repl)

    # ---------------- verify fully, in memory, before writing ----------------
    _, _, _, ents2 = parse_arc_bytes(data)
    assert len(ents2) == len(entries), "entry count changed"
    nraws = dict((x.index, unpack(x)) for x in ents2)
    for a, b in zip(entries, ents2):
        assert a.name == b.name and a.type_hash == b.type_hash and a.flags == b.flags
        if a.index not in repl:
            assert nraws[b.index] == raws[a.index], "untouched entry %d changed" % a.index
    nby = {}
    for x in ents2: nby.setdefault((x.name, nraws[x.index][:4]), x.index)
    for x in ents2:
        if nraws[x.index][:4] != b"\0GSM": continue
        fi2 = nby.get((x.name, b"\0FIM"))
        if fi2 is None: continue
        o_f = raws[by[(x.name, b"\0FIM")]]
        n_f = nraws[fi2]
        n1 = struct.unpack_from(">I", n_f, 8)[0]; base = 32 + n1*20
        assert len(n_f) == len(o_f), "FIM length changed"
        assert n_f[:base] == o_f[:base], "FIM primary table changed"
        n2 = struct.unpack_from(">I", n_f, 12)[0]
        for j in range(n2):
            o = base + j*44
            a_ = struct.unpack_from(">11I", o_f, o)
            b_ = struct.unpack_from(">11I", n_f, o)
            for c in range(11):
                if a_[c] == b_[c]: continue
                if c == 0: continue
                if c == 1 and (a_[c] & 0xFFFF) == (b_[c] & 0xFFFF): continue
                raise AssertionError("FIM secondary col%d changed at %d" % (c, j))
        # contract must hold
        w2, base2 = desired(nraws[x.index], n_f)
        for j in w2:
            lines, glyphs, s = w2[j]
            c0, c1 = struct.unpack_from(">II", n_f, base2 + j*44)
            assert c0 == ((lines << 16) | glyphs) and (c1 >> 16) == s, "contract violated"
        # record count unchanged
        assert struct.unpack_from(">I", nraws[x.index], 12)[0] == \
               struct.unpack_from(">I", raws[by[(x.name, b"\0GSM")]], 12)[0], "GSM record count changed"

    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP / path.name)
    path.write_bytes(data)
    return "repaired", fixed, log

def main():
    files = sorted(ENG.glob("msg_m*_pl*.arc"))
    rep = []; untrans = []; errs = []
    tot = 0; nrep = 0; nclean = 0
    for k, p in enumerate(files, 1):
        if "_backup" in p.name: continue
        try:
            status, fixed, log = process(p)
            if status == "skipped_untranslated": untrans.append(p.name)
            elif status == "repaired":
                nrep += 1; tot += fixed
                rep.append({"file": p.name, "inserted": fixed, "detail": log})
            else: nclean += 1
        except Exception as ex:
            errs.append({"file": p.name, "error": "%s: %s" % (type(ex).__name__, ex)})
            print("  ERROR %s: %s" % (p.name, ex))
        if k % 200 == 0: print("  [%d/%d] repaired=%d inserted=%d" % (k, len(files), nrep, tot))
    WORK.mkdir(parents=True, exist_ok=True)
    summary = {"archives": len(files), "repaired_archives": nrep,
               "spaces_inserted": tot, "already_clean": nclean,
               "skipped_untranslated": untrans, "errors": errs}
    (WORK/"GLUED_RUN_REPORT.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (WORK/"GLUED_RUN_DETAIL.json").write_text(json.dumps(rep), encoding="utf-8")
    print("\n" + "="*56)
    print("  archives                %d" % len(files))
    print("  archives repaired       %d" % nrep)
    print("  spaces inserted         %d" % tot)
    print("  already clean           %d" % nclean)
    print("  skipped (untranslated)  %d" % len(untrans))
    print("  errors                  %d" % len(errs))
    print("="*56)
    if untrans:
        print("  untranslated archives:", ", ".join(untrans[:20]),
              "..." if len(untrans) > 20 else "")
    print("\n  originals backed up to: %s" % BACKUP)
    return 0

if __name__ == "__main__":
    sys.exit(main())
