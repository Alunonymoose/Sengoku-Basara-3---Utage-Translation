#!/usr/bin/env python3
"""xetcli -- command-line front end for the canonical utage_xet codec.

  python xetcli.py info      <file.xet>
  python xetcli.py decode    <file.xet> <out.png> [--storage]
  python xetcli.py graft     <target.xet> <candidate.png> <out.xet> [--mask m.png] [--prefill dilate|none|colour --colour R,G,B]
  python xetcli.py arc-list  <file.arc>
  python xetcli.py arc-graft <file.arc> <member index|name> <candidate.png> <out.arc> [--mask m.png] [--prefill ...]
  python xetcli.py scan      <eng.arc> <ref.arc>
  python xetcli.py census    <rom/eng dir> [--ref <rom/jpn dir>] [--out census.json]

Candidates, masks and previews are DISPLAY-space PNGs (what the game shows).
Outputs are written beside nothing: you choose every output path, and
nothing here writes into rom/. Install into live E: stays a separate,
backed-up step (see the utage-session-start install protocol).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import utage_xet as ux  # noqa: E402

SAFE_ARC = HERE.parents[1] / "tools" / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
SAFE_ARC_SHA256 = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"


def load_safe_arc():
    data = SAFE_ARC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SAFE_ARC_SHA256:
        sys.exit(f"safe_arc.py hash mismatch; expected pinned {SAFE_ARC_SHA256}")
    spec = importlib.util.spec_from_file_location("safe_arc", SAFE_ARC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_png(path) -> np.ndarray:
    from PIL import Image
    return np.array(Image.open(path).convert("RGBA"))


def write_png(path, arr) -> None:
    from PIL import Image
    Image.fromarray(np.asarray(arr, np.uint8), "RGBA").save(path)


def read_mask(path):
    if not path:
        return None
    from PIL import Image
    return np.array(Image.open(path).convert("L")) > 127


def _colour(s):
    return tuple(int(v) for v in s.split(",")) if s else None


def _info_dict(raw: bytes) -> dict:
    i = ux.xet_info(raw)
    d = {"width": i.width, "height": i.height, "format": f"0x{i.format_code:02X}", "codec": i.codec,
         "semantics": i.semantics, "mips": i.mip_count, "swizzle": i.swizzle, "version": f"0x{i.version:X}",
         "writable": bool(ux.FORMATS.get(i.format_code, ("", "", False, False))[3]) and i.mip_count == 1 and i.swizzle == 0,
         "sha256": ux.sha256(raw)}
    if i.semantics.startswith("ycbcr") and i.swizzle == 0:
        d["byte_order_evidence"] = ux.byte_order_evidence(raw)
    return d


def _is_xet(raw: bytes) -> bool:
    return raw[:4] == ux.MAGIC


def _entries(sa, data: bytes):
    """Strict parse; fall back to read-only lenient listing for special ARCs."""
    try:
        return sa.parse_arc(data), True
    except ValueError:
        import struct
        import zlib
        count = struct.unpack_from(">H", data, 6)[0]
        out = []
        for k in range(count):
            rec = data[8 + 80 * k: 8 + 80 * (k + 1)]
            _th, size, packed, off = struct.unpack_from(">IIII", rec, 64)
            stored = data[off:off + size]
            try:
                raw = zlib.decompress(stored)
            except zlib.error:
                raw = stored
            out.append({"index": k, "name": rec[:64].split(b"\0", 1)[0].decode("utf-8", "replace"), "raw": raw})
        return out, False


def cmd_info(a):
    print(json.dumps(_info_dict(Path(a.xet).read_bytes()), indent=2))


def cmd_decode(a):
    raw = Path(a.xet).read_bytes()
    write_png(a.out, ux.decode_storage(raw) if a.storage else ux.decode_display(raw))
    print(f"wrote {a.out} ({'storage' if a.storage else 'display'})")


def cmd_graft(a):
    raw = Path(a.target).read_bytes()
    out, rep = ux.graft(raw, read_png(a.candidate), mask=read_mask(a.mask), prefill=a.prefill,
                        prefill_colour=_colour(a.colour), allow_inconclusive_byte_order=a.allow_inconclusive)
    Path(a.out).write_bytes(out)
    Path(a.out + ".graft.json").write_text(rep.to_json())
    write_png(a.out + ".final_display.png", ux.decode_display(out))
    print(rep.to_json())


def cmd_arc_list(a):
    sa = load_safe_arc()
    entries, strict = _entries(sa, Path(a.arc).read_bytes())
    rows = []
    for e in entries:
        if _is_xet(e["raw"]):
            try:
                rows.append({"index": e["index"], "name": e["name"], **_info_dict(e["raw"])})
            except ux.XetError as exc:
                rows.append({"index": e["index"], "name": e["name"], "error": str(exc)})
    print(json.dumps({"strict_parse": strict, "textures": rows}, indent=2))


def _find(entries, key):
    if key.isdigit():
        return entries[int(key)]
    hits = [e for e in entries if e["name"] == key or e["name"].endswith(key)]
    if len(hits) != 1:
        sys.exit(f"member {key!r} matched {len(hits)} entries")
    return hits[0]


def cmd_arc_graft(a):
    sa = load_safe_arc()
    src = Path(a.arc).read_bytes()
    entries = sa.parse_arc(src)  # strict: mutation is fail-closed on special ARCs
    e = _find(entries, a.member)
    new_xet, rep = ux.graft(e["raw"], read_png(a.candidate), mask=read_mask(a.mask), prefill=a.prefill,
                            prefill_colour=_colour(a.colour), allow_inconclusive_byte_order=a.allow_inconclusive)
    out = sa.rebuild_arc(src, {e["index"]: new_xet})
    arc_rep = sa.verify_rebuild(src, out, {e["index"]: new_xet})
    # re-extract from the FINAL ARC and decode what the game will load
    final = sa.parse_arc(out)[e["index"]]["raw"]
    if final != new_xet:
        sys.exit("re-extracted member differs from grafted XET")
    Path(a.out).write_bytes(out)
    write_png(a.out + f".member{e['index']}.final_display.png", ux.decode_display(final))
    record = {"arc_source_sha256": ux.sha256(src), "arc_output_sha256": ux.sha256(out),
              "member": {"index": e["index"], "name": e["name"]}, "graft": json.loads(rep.to_json()),
              "arc_verify": arc_rep, "final_member_sha256": ux.sha256(final),
              "evidence_level": "STRUCTURALLY VERIFIED -- needs duplicate-provider check + RPCS3 cold boot"}
    Path(a.out + ".record.json").write_text(json.dumps(record, indent=2, default=str))
    print(json.dumps(record, indent=2, default=str))


def _scan_pair(sa, eng_arc: bytes, ref_arc: bytes) -> list:
    e_entries, _ = _entries(sa, eng_arc)
    r_entries, _ = _entries(sa, ref_arc)
    ref_by_name = {e["name"]: e for e in r_entries}
    rows = []
    for e in e_entries:
        if not _is_xet(e["raw"]):
            continue
        try:
            info = ux.xet_info(e["raw"])
            if not info.semantics.startswith("ycbcr") or info.swizzle:
                continue
            row = {"index": e["index"], "name": e["name"], "byte_order": ux.byte_order_evidence(e["raw"])}
            ref = ref_by_name.get(e["name"])
            if ref is not None and _is_xet(ref["raw"]):
                row["vs_reference"] = ux.scan_against_reference(e["raw"], ref["raw"])
            rows.append(row)
        except ux.XetError as exc:
            rows.append({"index": e["index"], "name": e["name"], "error": str(exc)})
    return rows


def cmd_scan(a):
    sa = load_safe_arc()
    print(json.dumps(_scan_pair(sa, Path(a.eng).read_bytes(), Path(a.ref).read_bytes()), indent=2))


def cmd_census(a):
    """Every 0x2A/0x2B texture under rom/eng: byte-order verdict and, with
    --ref, changed-block legacy-encoding suspicion. Read-only."""
    sa = load_safe_arc()
    root = Path(a.eng)
    ref_root = Path(a.ref) if a.ref else None
    report = {"tool": f"utage_xet {ux.__version__}", "eng": str(root), "ref": str(ref_root) if ref_root else None,
              "archives": []}
    for arc in sorted(root.rglob("*.arc")):
        rel = arc.relative_to(root)
        try:
            eng_bytes = arc.read_bytes()
            ref_path = ref_root / rel if ref_root else None
            ref_bytes = ref_path.read_bytes() if ref_path and ref_path.exists() else None
            if ref_bytes is not None:
                rows = _scan_pair(sa, eng_bytes, ref_bytes)
            else:
                entries, _ = _entries(sa, eng_bytes)
                rows = []
                for e in entries:
                    if _is_xet(e["raw"]):
                        try:
                            i = ux.xet_info(e["raw"])
                            if i.semantics.startswith("ycbcr") and not i.swizzle:
                                rows.append({"index": e["index"], "name": e["name"],
                                             "byte_order": ux.byte_order_evidence(e["raw"])})
                        except ux.XetError as exc:
                            rows.append({"index": e["index"], "name": e["name"], "error": str(exc)})
        except Exception as exc:  # read-only census: record and continue
            report["archives"].append({"arc": str(rel), "error": repr(exc)})
            continue
        flagged = [r for r in rows if r.get("byte_order", {}).get("verdict") == "swapped"
                   or r.get("vs_reference", {}).get("suspect_legacy_encoding")]
        if rows:
            report["archives"].append({"arc": str(rel), "sha256": ux.sha256(eng_bytes),
                                       "ycbcr_textures": len(rows), "flagged": flagged})
    report["flagged_total"] = sum(len(x.get("flagged", [])) for x in report["archives"])
    text = json.dumps(report, indent=2)
    if a.out:
        Path(a.out).write_text(text)
        print(f"wrote {a.out}; flagged textures: {report['flagged_total']}")
    else:
        print(text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("xet"); s.set_defaults(fn=cmd_info)
    s = sub.add_parser("decode"); s.add_argument("xet"); s.add_argument("out"); s.add_argument("--storage", action="store_true"); s.set_defaults(fn=cmd_decode)
    for name, fn in (("graft", cmd_graft), ("arc-graft", cmd_arc_graft)):
        s = sub.add_parser(name)
        if name == "graft":
            s.add_argument("target")
        else:
            s.add_argument("arc"); s.add_argument("member")
        s.add_argument("candidate"); s.add_argument("out")
        s.add_argument("--mask"); s.add_argument("--prefill", default="dilate", choices=["dilate", "none", "colour"])
        s.add_argument("--colour"); s.add_argument("--allow-inconclusive", action="store_true")
        s.set_defaults(fn=fn)
    s = sub.add_parser("arc-list"); s.add_argument("arc"); s.set_defaults(fn=cmd_arc_list)
    s = sub.add_parser("scan"); s.add_argument("eng"); s.add_argument("ref"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("census"); s.add_argument("eng"); s.add_argument("--ref"); s.add_argument("--out"); s.set_defaults(fn=cmd_census)
    a = p.parse_args(argv)
    try:
        a.fn(a)
    except ux.XetError as exc:
        sys.exit(f"REFUSED: {exc}")


if __name__ == "__main__":
    main()
