#!/usr/bin/env python3
"""
UTAGE - SEPARATOR GLYPH REPAIR

Replaces the un-re-encoded Japanese glyph sitting in the name/message
separator slot (immediately after FF91) with a space (0x0000).

Capcom's structure:   [FF92]<name>[FF91]<message-ref>
Ours:                 [FF92]<name>[FF91] 0062 "Take them down!"

0x0062 is a leftover Japanese ordinal; the 184-glyph Latin font draws it
as "£". PROVEN on hardware 2026-09-14: replacing it with a space renders
"Harumasa Nanbu Take them down!" correctly, with no regression.

Only touches a glyph that: follows FF91, is < 184 (i.e. actually drawn),
decodes outside printable ASCII, and has real text after it.
Untranslated archives (font >= 600 glyphs) are skipped.
Originals are backed up before writing.
"""
import json, shutil, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from FIM_CONTRACT_REPAIR import (ROOT, ENG, parse_arc, unpack, rebuild,
                                 parse_arc_bytes, gsm_records, tokens, desired)
from GLUED_RUN_REPAIR import build_gsm, dec, font_glyphs

WORK   = ROOT / "_FIM_CONTRACT_REPAIR"
BACKUP = ROOT / "_SEPARATOR_BACKUP"

def process(path):
    data0, endian, version, entries = parse_arc(path)
    raws = dict((e.index, unpack(e)) for e in entries)
    gc = font_glyphs(entries, raws)
    if gc is None or gc >= 600:
        return "skipped_untranslated", 0
    by = {}
    for e in entries: by.setdefault((e.name, raws[e.index][:4]), e.index)

    repl = {}; n = 0
    for e in entries:
        if raws[e.index][:4] != b"\0GSM": continue
        if (e.name, b"\0FIM") not in by: continue
        recs = gsm_records(raws[e.index]); changed = False
        for ri, rec in enumerate(recs):
            try: ts = tokens(rec)
            except Exception: break
            new = list(rec); hit = False
            for k in range(len(ts)):
                o, v, vs = ts[k]
                if v != 0xFF91 or k + 1 >= len(ts): continue
                o2, v2, _ = ts[k+1]
                if v2 >= 0x8000 or v2 >= 184: continue
                if dec(v2) is not None: continue
                rest = ts[k+2:]
                if not any(w < 0x8000 and dec(w) is not None for _, w, _ in rest):
                    continue
                new[o2] = 0x0000; hit = True; n += 1
            if hit:
                recs[ri] = new; changed = True
        if changed:
            repl[e.index] = build_gsm(raws[e.index], recs)

    if not repl: return "clean", 0

    for e in entries:
        if raws[e.index][:4] != b"\0GSM": continue
        fi = by.get((e.name, b"\0FIM"))
        if fi is None: continue
        g = repl.get(e.index, raws[e.index]); f = repl.get(fi, raws[fi])
        want, base = desired(g, f)
        out = bytearray(f)
        for j in want:
            lines, glyphs, s = want[j]
            o = base + j*44
            struct.pack_into(">I", out, o, (lines << 16) | glyphs)
            struct.pack_into(">H", out, o+4, s)
        repl[fi] = bytes(out)

    newdata = rebuild(data0, endian, entries, repl)

    _, _, _, ents2 = parse_arc_bytes(newdata)
    assert len(ents2) == len(entries)
    nraws = dict((x.index, unpack(x)) for x in ents2)
    for a, b in zip(entries, ents2):
        assert a.name == b.name and a.type_hash == b.type_hash and a.flags == b.flags
        if a.index not in repl:
            assert nraws[b.index] == raws[a.index], "untouched entry changed"
    nby = {}
    for x in ents2: nby.setdefault((x.name, nraws[x.index][:4]), x.index)
    for x in ents2:
        if nraws[x.index][:4] != b"\0GSM": continue
        fi2 = nby.get((x.name, b"\0FIM"))
        if fi2 is None: continue
        of = raws[by[(x.name, b"\0FIM")]]; nf = nraws[fi2]
        n1 = struct.unpack_from(">I", nf, 8)[0]; base = 32 + n1*20
        assert len(nf) == len(of) and nf[:base] == of[:base], "FIM primary changed"
        n2 = struct.unpack_from(">I", nf, 12)[0]
        for j in range(n2):
            o = base + j*44
            A = struct.unpack_from(">11I", of, o); B = struct.unpack_from(">11I", nf, o)
            for c in range(11):
                if A[c] == B[c]: continue
                if c == 0: continue
                if c == 1 and (A[c] & 0xFFFF) == (B[c] & 0xFFFF): continue
                raise AssertionError("FIM col%d changed" % c)
        w, bs = desired(nraws[x.index], nf)
        for j in w:
            lines, glyphs, s = w[j]
            c0, c1 = struct.unpack_from(">II", nf, bs + j*44)
            assert c0 == ((lines << 16) | glyphs) and (c1 >> 16) == s, "contract violated"
        assert struct.unpack_from(">I", nraws[x.index], 12)[0] == \
               struct.unpack_from(">I", raws[by[(x.name, b"\0GSM")]], 12)[0]

    BACKUP.mkdir(parents=True, exist_ok=True)
    if not (BACKUP / path.name).exists():
        shutil.copy2(path, BACKUP / path.name)
    path.write_bytes(newdata)
    return "repaired", n

def main():
    files = sorted(ENG.glob("msg_m*_pl*.arc"))
    nrep = nclean = nskip = 0; tot = 0; errs = []
    for k, p in enumerate(files, 1):
        if "_backup" in p.name: continue
        try:
            st, n = process(p)
            if st == "repaired": nrep += 1; tot += n
            elif st == "clean": nclean += 1
            else: nskip += 1
        except Exception as ex:
            errs.append({"file": p.name, "error": "%s: %s" % (type(ex).__name__, ex)})
            print("  ERROR %s: %s" % (p.name, ex))
        if k % 300 == 0: print("  [%d/%d] repaired=%d replaced=%d" % (k, len(files), nrep, tot))
    s = {"archives": len(files), "repaired_archives": nrep, "separators_replaced": tot,
         "already_clean": nclean, "skipped_untranslated": nskip, "errors": errs}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK/"SEPARATOR_REPORT.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    print("\n" + "="*52)
    for k2 in ("archives","repaired_archives","separators_replaced","already_clean","skipped_untranslated"):
        print("  %-22s %d" % (k2, s[k2]))
    print("  errors                 %d" % len(errs))
    print("="*52)
    print("  originals backed up to: %s" % BACKUP)
    return 0

if __name__ == "__main__":
    sys.exit(main())
