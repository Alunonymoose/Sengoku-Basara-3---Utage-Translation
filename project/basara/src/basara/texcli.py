#!/usr/bin/env python3
"""basara tex -- texture commands on the canonical XET codec (basara.xet).

  basara tex info      <file.xet>
  basara tex decode    <file.xet> <out.png> [--storage]
  basara tex graft     <target.xet> <candidate.png> <out.xet> [--mask m.png] [--prefill dilate|none|colour --colour R,G,B]
  basara tex arc-list  <file.arc>
  basara tex arc-graft <file.arc> <member index|name> <candidate.png> <out.arc> [--mask m.png] [--prefill ...]
  basara tex scan      <eng.arc> <ref.arc>
  basara tex census    <rom/eng dir> [--ref <rom/jpn dir>] [--out census.json]

Candidates, masks and previews are DISPLAY-space PNGs (what the game shows).
Outputs are written beside nothing: you choose every output path, and
nothing here writes into rom/. Install into live E: stays a separate,
backed-up step (see the utage-session-start install protocol).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import arc as arcmod
from . import xet as ux


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


def _entries(data: bytes):
    """Strict parse; fall back to lenient read-only listing for special ARCs."""
    try:
        return arcmod.read(data), True
    except arcmod.ArcError:
        return arcmod.inspect(data), False


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
    archive, strict = _entries(Path(a.arc).read_bytes())
    rows = []
    for e in archive:
        if e.magic == ux.MAGIC:
            try:
                rows.append({"index": e.index, "name": e.name, **_info_dict(e.raw)})
            except ux.XetError as exc:
                rows.append({"index": e.index, "name": e.name, "error": str(exc)})
    print(json.dumps({"strict_parse": strict, "textures": rows}, indent=2))


def _find(archive, key):
    try:
        return archive.find(int(key) if key.isdigit() else key)
    except arcmod.ArcError as exc:
        sys.exit(str(exc))


def cmd_arc_graft(a):
    src = Path(a.arc).read_bytes()
    archive = arcmod.read(src)  # strict: mutation is fail-closed on special ARCs
    e = _find(archive, a.member)
    new_xet, rep = ux.graft(e.raw, read_png(a.candidate), mask=read_mask(a.mask), prefill=a.prefill,
                            prefill_colour=_colour(a.colour), allow_inconclusive_byte_order=a.allow_inconclusive)
    out = arcmod.rebuild(src, {e.index: new_xet})
    arc_rep = arcmod.verify_rebuild(src, out, {e.index: new_xet})
    # re-extract from the FINAL ARC and decode what the game will load
    final = arcmod.read(out)[e.index].raw
    if final != new_xet:
        sys.exit("re-extracted member differs from grafted XET")
    Path(a.out).write_bytes(out)
    write_png(a.out + f".member{e.index}.final_display.png", ux.decode_display(final))
    record = {"arc_source_sha256": ux.sha256(src), "arc_output_sha256": ux.sha256(out),
              "member": {"index": e.index, "name": e.name}, "graft": json.loads(rep.to_json()),
              "arc_verify": arc_rep, "final_member_sha256": ux.sha256(final),
              "evidence_level": "STRUCTURALLY VERIFIED -- needs duplicate-provider check + RPCS3 cold boot"}
    Path(a.out + ".record.json").write_text(json.dumps(record, indent=2, default=str))
    print(json.dumps(record, indent=2, default=str))


def _ycbcr_rows(archive, ref_archive=None) -> list:
    ref_by_name = {e.name: e for e in ref_archive} if ref_archive is not None else {}
    rows = []
    for e in archive:
        if e.magic != ux.MAGIC:
            continue
        try:
            info = ux.xet_info(e.raw)
            if not info.semantics.startswith("ycbcr") or info.swizzle:
                continue
            row = {"index": e.index, "name": e.name, "byte_order": ux.byte_order_evidence(e.raw)}
            ref = ref_by_name.get(e.name)
            if ref is not None and ref.magic == ux.MAGIC:
                row["vs_reference"] = ux.scan_against_reference(e.raw, ref.raw)
            rows.append(row)
        except (ux.XetError, arcmod.ArcError) as exc:
            rows.append({"index": e.index, "name": e.name, "error": str(exc)})
    return rows


def cmd_scan(a):
    eng, _ = _entries(Path(a.eng).read_bytes())
    ref, _ = _entries(Path(a.ref).read_bytes())
    print(json.dumps(_ycbcr_rows(eng, ref), indent=2))


def cmd_census(a):
    """Every 0x2A/0x2B texture under rom/eng: byte-order verdict and, with
    --ref, changed-block legacy-encoding suspicion. Read-only."""
    root = Path(a.eng)
    ref_root = Path(a.ref) if a.ref else None
    report = {"tool": f"basara.xet {ux.__version__}", "eng": str(root), "ref": str(ref_root) if ref_root else None,
              "archives": []}
    for arc_path in sorted(root.rglob("*.arc")):
        rel = arc_path.relative_to(root)
        try:
            eng_bytes = arc_path.read_bytes()
            eng, _ = _entries(eng_bytes)
            ref_path = ref_root / rel if ref_root else None
            ref = _entries(ref_path.read_bytes())[0] if ref_path and ref_path.exists() else None
            rows = _ycbcr_rows(eng, ref)
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
    p = argparse.ArgumentParser(prog="basara tex", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
