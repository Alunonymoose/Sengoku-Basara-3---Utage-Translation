#!/usr/bin/env python3
"""
UTAGE - TEXT DEFECT SCAN (read-only, writes no game files)

Finds three classes of rendering defect in rom\eng\id:

  A. STRAY GLYPH - a text glyph that decodes outside printable ASCII.
     These are Japanese glyph ordinals that were never re-encoded; the
     184-glyph Latin font draws them as garbage (e.g. 0x0062 -> "£").
     They pass the old invariant check because 0x62 < 184.

  B. GLUED RUNS - a styled run (FF92..FF91) butting directly against
     adjacent text with no space, so it renders as one fused word
     (e.g. "...of the Dead" + "effect has ended" -> "Deadeffect has ended").

  C. OVERLONG LINE - a visual line wider than the plate can draw.
"""
import json, struct, sys, zlib
from pathlib import Path

ROOT = Path(r"E:\Utage Patching New")
ENG  = ROOT / "PS3_GAME/USRDIR/nativePS3/rom/eng/id"
WORK = ROOT / "_FIM_CONTRACT_REPAIR"
LINE_LIMIT = 41

ARGC = {0xFC0E:2, 0xFC0F:1, 0xFC12:0, 0xFC16:1, 0xFC17:3, 0xFED2:2, 0xFF91:0,
        0xFF92:1, 0xFFFA:1, 0xFFFB:1, 0xFFFD:0, 0xFFFE:0, 0xFFFF:0}
ENTRY_SIZE = 80; TABLE_START = 8

class E(object):
    __slots__=("index","name","type_hash","csize","raw_size","flags","off","compressed")

def parse_arc(path):
    data = path.read_bytes(); magic = data[:4]
    endian = ">" if magic == b"\x00CRA" else "<"
    version, count = struct.unpack_from(endian+"HH", data, 4)
    ents=[]
    for i in range(count):
        o = TABLE_START + i*ENTRY_SIZE
        name = data[o:o+64].split(b"\0",1)[0].decode("ascii","replace")
        th, cs, packed, off = struct.unpack_from(endian+"IIII", data, o+64)
        e=E(); e.index,e.name,e.type_hash=i,name,th
        e.csize,e.raw_size,e.flags=cs,packed>>3,packed&7
        e.off=off; e.compressed=data[off:off+cs]; ents.append(e)
    return ents

def unpack(e):
    return e.compressed if e.csize==e.raw_size else zlib.decompress(e.compressed)

def gsm_records(raw):
    units,count=struct.unpack_from(">II",raw,8); start=16+count*8
    recs=[]
    for i in range(count):
        off,n=struct.unpack_from(">II",raw,16+i*8)
        recs.append(list(struct.unpack_from(">"+str(n)+"H",raw,start+off*2)))
    return recs

def dec(g):
    c = g+32 if g < 0x06 else g+33
    return chr(c) if 32 <= c <= 126 else None

def toks(seq):
    r=[];i=0
    while i<len(seq):
        v=seq[i]
        if v>=0xF000:
            if v not in ARGC: raise ValueError("unknown control %04X"%v)
            n=1+ARGC[v]
        else: n=1
        if i+n>len(seq): raise ValueError("truncated")
        r.append((i,v,seq[i:i+n])); i+=n
    return r

def scan(path):
    out=[]
    for e in parse_arc(path):
        raw=unpack(e)
        if raw[:4]!=b"\0GSM": continue
        try: recs=gsm_records(raw)
        except Exception: continue
        for ri,r in enumerate(recs):
            try: ts=toks(r)
            except Exception: break
            # A. stray glyphs
            for o,v,vs in ts:
                if v<0x8000 and dec(v) is None:
                    out.append({"res":e.name,"rec":ri,"kind":"STRAY_GLYPH",
                                "glyph":"0x%04X"%v,"at":o})
            # B. glued styled runs + C. overlong lines
            line=[]; lines=[]
            styled=False; prev_char=None; first_styled=None
            for o,v,vs in ts:
                if v==0xFFFE or v==0xFFFD:
                    lines.append("".join(line)); line=[]; prev_char=None; continue
                if v==0xFF92: styled=True; first_styled=True; continue
                if v==0xFF91: styled=False; continue
                if v>=0x8000: prev_char=None; continue
                ch=dec(v)
                if ch is None: continue
                if first_styled and prev_char is not None:
                    if prev_char not in " \n" and ch not in " ,.!?:;'-\n":
                        out.append({"res":e.name,"rec":ri,"kind":"GLUED_RUN",
                                    "at":o,"join":prev_char+"|"+ch})
                    first_styled=False
                elif first_styled:
                    first_styled=False
                line.append(ch); prev_char=ch
            lines.append("".join(line))
            for li,L in enumerate(lines):
                if len(L) > LINE_LIMIT:
                    out.append({"res":e.name,"rec":ri,"kind":"OVERLONG_LINE",
                                "len":len(L),"line":L[:70]})
    return out

def main():
    files=sorted(ENG.glob("msg_m*_pl*.arc"))
    allf=[]; bykind={}
    for k,p in enumerate(files,1):
        if "_backup" in p.name: continue
        try:
            for d in scan(p):
                d["file"]=p.name; allf.append(d)
                bykind[d["kind"]]=bykind.get(d["kind"],0)+1
        except Exception as ex:
            print("  ERROR %s: %s"%(p.name,ex))
        if k%200==0: print("  [%d/%d] findings=%d"%(k,len(files),len(allf)))
    WORK.mkdir(parents=True,exist_ok=True)
    (WORK/"TEXT_DEFECT_SCAN.json").write_text(json.dumps(allf),encoding="utf-8")
    # summaries
    strays={}
    for d in allf:
        if d["kind"]=="STRAY_GLYPH": strays[d["glyph"]]=strays.get(d["glyph"],0)+1
    summary={"counts":bykind,"stray_glyph_histogram":strays,
             "files_scanned":len(files),
             "files_with_findings":len(set(d["file"] for d in allf))}
    (WORK/"TEXT_DEFECT_SUMMARY.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print("\n"+"="*56)
    for k in sorted(bykind): print("  %-16s %d"%(k,bykind[k]))
    print("  stray glyph values:", strays)
    print("  files with findings:", summary["files_with_findings"], "of", len(files))
    print("="*56)
    for d in allf[:15]: print("   ",d)
    return 0

if __name__=="__main__": sys.exit(main())
