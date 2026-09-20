#!/usr/bin/env python3
"""
UTAGE - FIM FORMAT CONTRACT REPAIR
==================================

WHAT THIS FIXES
---------------
Each \0FIM secondary row ("format record") carries two fields that are derived
from the GSM message text it describes:

    col0        = (visual_line_count << 16) | visible_glyph_count
    col1 high16 = the speech's START OFFSET (in GSM units) inside its record

The English rewrite changed the text, which changes both. The budget (col0) was
only partly maintained and the start offset (col1) was never updated at all, so
the engine reveals the wrong number of characters and reads speeches from stale
offsets. That is the runaway / truncated / looping dialogue.

WHY THE RULE IS TRUSTED
-----------------------
With the corrected control grammar below, this contract holds with ZERO
exceptions across:
    pristine Japanese Utage          1,469,782 format records
    official Capcom Samurai Heroes     246,404 format records
Two shipped commercial builds, no counterexamples.

Corrected control argument counts (this is what makes the parse work):
    0xFC17 takes 3 arguments   (previously assumed 1)
    0xFF91 takes 0 arguments   (previously assumed 1)
    0xFFFD delimits speeches;  0xFFFE increments the visual line count

WHAT IT TOUCHES
---------------
Only col0 (4 bytes) and the high half of col1 (2 bytes) of each format record.
Everything else is byte-identical: the GSM text, the voice links (col8), the
event links (primary col4), every texture, every other archive member.

Every changed value is recorded in FIM_CONTRACT_REPAIR_UNDO.json so the repair
is exactly reversible with FIM_CONTRACT_ROLLBACK.py.
"""

import json, os, struct, sys, zlib, time
from pathlib import Path

ROOT = Path(r"E:\Utage Patching New")
ENG  = ROOT / "PS3_GAME/USRDIR/nativePS3/rom/eng/id"
WORK = ROOT / "_FIM_CONTRACT_REPAIR"

ARGC = {0xFC0E:2, 0xFC0F:1, 0xFC12:0, 0xFC16:1, 0xFC17:3, 0xFED2:2, 0xFF91:0,
        0xFF92:1, 0xFFFA:1, 0xFFFB:1, 0xFFFD:0, 0xFFFE:0, 0xFFFF:0}
# 0xFC0E solved by exhaustive search against the contract: argc=2 is the only
# value giving zero violations on pristine JP msg_m007_pl005 (990 formats),
# pristine JP msg_m001_pl017 (1298) and official SH msg_pl000_m000 (632).

ENTRY_SIZE = 80
TABLE_START = 8

# ---------------------------------------------------------------- ARC v8 ----

class Entry(object):
    __slots__ = ("index","name","type_hash","csize","raw_size","flags","off","compressed")

def parse_arc(path):
    data = path.read_bytes()
    magic = data[:4]
    if magic == b"\x00CRA": endian = ">"
    elif magic == b"ARC\x00": endian = "<"
    else: raise ValueError("not an ARC: %r" % magic)
    version, count = struct.unpack_from(endian+"HH", data, 4)
    entries = []
    for i in range(count):
        o = TABLE_START + i*ENTRY_SIZE
        name = data[o:o+64].split(b"\0",1)[0].decode("ascii","replace")
        type_hash, csize, packed, off = struct.unpack_from(endian+"IIII", data, o+64)
        e = Entry()
        e.index, e.name, e.type_hash = i, name, type_hash
        e.csize, e.raw_size, e.flags = csize, packed >> 3, packed & 7
        e.off = off
        e.compressed = data[off:off+csize]
        entries.append(e)
    return data, endian, version, entries

def unpack(e):
    if e.csize == e.raw_size: return e.compressed
    return zlib.decompress(e.compressed)

def rebuild(data, endian, entries, replacements):
    offs = sorted(set(e.off for e in entries))
    alignment = 1
    for a in (2048,1024,512,256,128,64,32,16,8,4):
        if all(o % a == 0 for o in offs): alignment = a; break
    first = min(e.off for e in entries)
    out = bytearray(data[:first])
    payloads, raws = [], []
    for e in entries:
        if e.index in replacements:
            raw = replacements[e.index]
            payloads.append(raw if e.csize == e.raw_size else zlib.compress(raw, 9))
            raws.append(len(raw))
        else:
            payloads.append(e.compressed); raws.append(e.raw_size)
    cursor = first; newoffs = []
    for p in payloads:
        cursor = (cursor + alignment - 1)//alignment*alignment
        if len(out) < cursor: out.extend(b"\0"*(cursor-len(out)))
        newoffs.append(cursor); out.extend(p); cursor += len(p)
    for e,p,r,o in zip(entries,payloads,raws,newoffs):
        struct.pack_into(endian+"IIII", out, TABLE_START + e.index*ENTRY_SIZE + 64,
                         e.type_hash, len(p), (r<<3)|e.flags, o)
    return bytes(out)

# ------------------------------------------------------------- contract ----

def gsm_records(raw):
    assert raw[:4] == b"\0GSM"
    units, count = struct.unpack_from(">II", raw, 8)
    start = 16 + count*8
    assert len(raw) == start + units*2, "GSM size check failed"
    recs = []
    for i in range(count):
        off, n = struct.unpack_from(">II", raw, 16 + i*8)
        recs.append(list(struct.unpack_from(">"+str(n)+"H", raw, start + off*2)))
    return recs

def tokens(seq):
    r = []; i = 0
    while i < len(seq):
        v = seq[i]
        if v >= 0xF000:
            if v not in ARGC: raise ValueError("unknown control %04X at %d" % (v,i))
            n = 1 + ARGC[v]
        else: n = 1
        if i+n > len(seq): raise ValueError("truncated control")
        r.append((i, v, seq[i:i+n])); i += n
    return r

def spans(seq, count):
    ts = tokens(seq)
    if count == 0:
        if any(v < 0x8000 for _,v,_ in ts): raise ValueError("text in zero-speech row")
        return []
    starts = [0] + [o+len(vs) for o,v,vs in ts if v == 0xFFFD and o+len(vs) < len(seq)-1]
    if len(starts) != count: raise ValueError("speech count %d != FIM %d" % (len(starts), count))
    return [(s, starts[i+1] if i+1 < len(starts) else len(seq)) for i,s in enumerate(starts)]

def desired(graw, fraw):
    rs = gsm_records(graw)
    n1, n2, nv = struct.unpack_from(">III", fraw, 8)
    base = 32 + n1*20
    if n1 != len(rs) or len(fraw) != base + n2*44: raise ValueError("FIM/GSM shape mismatch")
    want = {}
    for i, r in enumerate(rs):
        h = struct.unpack_from(">5I", fraw, 32 + i*20)
        count, first = h[3] >> 16, h[4]
        for sp, se in enumerate(spans(r, count)):
            s, e = se
            j = first + sp
            if j >= n2: raise ValueError("format index out of range")
            ts = tokens(r[s:e])
            glyphs = sum(v < 0x8000 for _,v,_ in ts)
            lines  = 1 + sum(v == 0xFFFE for _,v,_ in ts)
            if max(lines, glyphs, s) > 65535: raise ValueError("halfword overflow")
            val = (lines, glyphs, s)
            if j in want and want[j] != val: raise ValueError("conflicting shared format %d" % j)
            want[j] = val
    if set(want) != set(range(n2)):
        raise ValueError("%d unowned format records" % (n2 - len(want)))
    return want, base

# ---------------------------------------------------------------- repair ----

def repair_one(path):
    data, endian, version, entries = parse_arc(path)
    raws = dict((e.index, unpack(e)) for e in entries)
    by = {}
    for e in entries: by.setdefault((e.name, raws[e.index][:4]), e.index)
    repl = {}; undo = {}; nb = 0; no = 0
    for e in entries:
        if raws[e.index][:4] != b"\0GSM": continue
        fi = by.get((e.name, b"\0FIM"))
        if fi is None: continue
        fraw = raws[fi]
        want, base = desired(raws[e.index], fraw)
        out = bytearray(fraw); allowed = set(); rec = []
        for j in want:
            lines, glyphs, s = want[j]
            o = base + j*44
            c0, c1 = struct.unpack_from(">II", out, o)
            new0 = (lines << 16) | glyphs
            if c0 != new0 or (c1 >> 16) != s:
                rec.append([j, c0, c1 >> 16])
                if c0 != new0: nb += 1
                if (c1 >> 16) != s: no += 1
            struct.pack_into(">I", out, o, new0)
            struct.pack_into(">H", out, o+4, s)
            allowed.update(range(o, o+6))
        assert len(out) == len(fraw)
        assert all(a == b or i in allowed for i,(a,b) in enumerate(zip(fraw,out))), \
            "wrote outside col0/col1-high"
        if rec:
            undo[e.name] = rec; repl[fi] = bytes(out)
    if not repl: return None, 0, 0

    newdata = rebuild(data, endian, entries, repl)

    # ---- verify the rebuilt image fully, in memory, before touching disk ---
    d2, en2, v2, ents2 = parse_arc_bytes(newdata)
    assert len(ents2) == len(entries), "entry count changed"
    nraws = dict((e.index, unpack(e)) for e in ents2)
    for a, b in zip(entries, ents2):
        assert a.name == b.name and a.type_hash == b.type_hash and a.flags == b.flags, \
            "entry metadata changed"
        if a.index in repl: assert nraws[b.index] == repl[a.index], "replacement mismatch"
        else:               assert nraws[b.index] == raws[a.index], "untouched entry %d changed" % a.index
    nby = {}
    for e in ents2: nby.setdefault((e.name, nraws[e.index][:4]), e.index)
    for e in ents2:
        if nraws[e.index][:4] != b"\0GSM": continue
        fi2 = nby.get((e.name, b"\0FIM"))
        if fi2 is None: continue
        w2, base2 = desired(nraws[e.index], nraws[fi2])
        for j in w2:
            lines, glyphs, s = w2[j]
            c0, c1 = struct.unpack_from(">II", nraws[fi2], base2 + j*44)
            assert c0 == ((lines << 16)|glyphs) and (c1 >> 16) == s, \
                "contract still violated after repair"

    path.write_bytes(newdata)
    return undo, nb, no

def parse_arc_bytes(data):
    magic = data[:4]
    if magic == b"\x00CRA": endian = ">"
    elif magic == b"ARC\x00": endian = "<"
    else: raise ValueError("not an ARC: %r" % magic)
    version, count = struct.unpack_from(endian+"HH", data, 4)
    entries = []
    for i in range(count):
        o = TABLE_START + i*ENTRY_SIZE
        name = data[o:o+64].split(b"\0",1)[0].decode("ascii","replace")
        type_hash, csize, packed, off = struct.unpack_from(endian+"IIII", data, o+64)
        e = Entry()
        e.index, e.name, e.type_hash = i, name, type_hash
        e.csize, e.raw_size, e.flags = csize, packed >> 3, packed & 7
        e.off = off
        e.compressed = data[off:off+csize]
        entries.append(e)
    return data, endian, version, entries

def main():
    if not ENG.is_dir():
        print("!! not found: %s" % ENG); return 2
    WORK.mkdir(parents=True, exist_ok=True)
    files = sorted(ENG.glob("msg_m*_pl*.arc"))
    print("FIM contract repair over %d archives in" % len(files))
    print("  %s\n" % ENG)
    undo_all = {}; rep = []
    nb_tot = 0; no_tot = 0; fixed = 0; clean = 0; errors = []
    t0 = time.time()
    for k, p in enumerate(files, 1):
        try:
            u, nb, no = repair_one(p)
            if u is None:
                clean += 1
            else:
                undo_all[p.name] = u; fixed += 1; nb_tot += nb; no_tot += no
                rep.append({"file": p.name, "budgets": nb, "offsets": no})
        except Exception as ex:
            errors.append({"file": p.name, "error": "%s: %s" % (type(ex).__name__, ex)})
            print("  ERROR %s: %s: %s" % (p.name, type(ex).__name__, ex))
        if k % 100 == 0 or k == len(files):
            print("  [%4d/%d] repaired=%d clean=%d errors=%d" % (k, len(files), fixed, clean, len(errors)))
    dt = time.time() - t0
    # Merge with any undo record from an earlier pass, keeping the ORIGINAL
    # values already recorded. Never discard an existing rollback path.
    up = WORK/"FIM_CONTRACT_REPAIR_UNDO.json"
    if up.exists():
        try:
            prev = json.loads(up.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
        kept = 0
        for k in undo_all:
            if k not in prev:
                prev[k] = undo_all[k]; kept += 1
        print("  merged undo: %d pre-existing archives kept, %d newly recorded"
              % (len(prev) - kept, kept))
        undo_all = prev
    up.write_text(json.dumps(undo_all), encoding="utf-8")
    summary = {"archives": len(files), "repaired": fixed, "already_clean": clean,
               "errors": errors, "budgets_fixed": nb_tot, "offsets_fixed": no_tot,
               "seconds": round(dt,1), "eng_id": str(ENG)}
    (WORK/"FIM_CONTRACT_REPAIR_REPORT.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (WORK/"FIM_CONTRACT_REPAIR_DETAIL.json").write_text(json.dumps(rep), encoding="utf-8")
    print("\n" + "="*60)
    print("  archives        %d" % len(files))
    print("  repaired        %d" % fixed)
    print("  already clean   %d" % clean)
    print("  errors          %d" % len(errors))
    print("  budgets fixed   %d" % nb_tot)
    print("  offsets fixed   %d" % no_tot)
    print("  time            %.1fs" % dt)
    print("="*60)
    print("\nUndo record: %s" % (WORK/"FIM_CONTRACT_REPAIR_UNDO.json"))
    print("Rollback with: FIM_CONTRACT_ROLLBACK.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
