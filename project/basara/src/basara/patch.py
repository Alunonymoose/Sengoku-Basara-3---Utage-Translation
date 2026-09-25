"""Declarative patchsets: one reviewable TOML file -> verified ARCs -> safe install.

Replaces per-job build scripts and ROOT-READY ZIPs. A patchset says WHAT
changes; the engine proves nothing else did.

    schema = "basara.patchset/1"
    id = "equip-brief-first-frost"

    [[archive]]
    path   = "tenka/equip.arc"            # relative to the rom/eng root
    sha256 = "3ad82a3b..."                 # the exact live bytes this was authored against

      [[archive.text]]
      table  = "id_brief_r"                # GSM member name/suffix, or index
      record = 1464
      expect = "Sacred Tree Bow: First Frost{end}"   # optional stale guard (current markup)
      text   = "Sacred Tree Bow:{br}First Frost{end}"
      budget = 700                          # optional: max line width in TNF units
      font   = { tnf = 0, csa = 24 }        # optional explicit font members

      [[archive.texture]]
      member           = "kessen_001_ID_HQ"
      candidate        = "art/kessen_001.png"   # DISPLAY-space PNG
      candidate_sha256 = "..."                  # approval binding (required)
      mask             = "art/kessen_001_mask.png"  # optional
      prefill          = "dilate"

      [[archive.member]]                    # raw member replacement (donor)
      member        = 12
      source        = "donors/x.bin"
      source_sha256 = "..."

Paths inside a patchset are relative to the patchset file.

``build``   -> out/<path> + out/build.json (every input/output hash, every
               per-op verification). Deterministic.
``install`` -> verified backup of each live ARC, hash-guarded atomic replace,
               read-back, INSTALL_RECORD.json. Idempotent.
``rollback``-> restores backups only where live still equals our output.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from . import arc as arcmod
from .markup import placeables
from .table import FontRef, MessageTable

SCHEMA = "basara.patchset/1"
BUILD_SCHEMA = "basara.build/1"
INSTALL_SCHEMA = "basara.install/1"


class PatchError(ValueError):
    pass


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> dict:
    spec = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    if spec.get("schema") != SCHEMA:
        raise PatchError(f"{path}: schema must be {SCHEMA!r}")
    if not spec.get("id"):
        raise PatchError(f"{path}: patchset needs an id")
    for a in spec.get("archive", []):
        if not a.get("path") or not a.get("sha256"):
            raise PatchError("every [[archive]] needs path and sha256")
    return spec


# ------------------------------------------------------------------ build
def _text_ops(archive: arcmod.Archive, ops: list[dict], report: list) -> dict[int, bytes]:
    by_table: dict[Any, list[dict]] = {}
    for op in ops:
        key = (op["table"], json.dumps(op.get("font"), sort_keys=True))
        by_table.setdefault(key, []).append(op)
    replacements: dict[int, bytes] = {}
    for (table, _), group in by_table.items():
        font = group[0].get("font")
        t = MessageTable.open(archive, table, font=FontRef(**font) if font else None)
        before = {op["record"]: t.text(op["record"]) for op in group}
        for op in group:
            r = op["record"]
            if "expect" in op and before[r] != op["expect"]:
                raise PatchError(f"{table}#{r}: live text differs from expect "
                                 f"(patchset is stale)\n  live:   {before[r]!r}\n  expect: {op['expect']!r}")
            if not op.get("allow_structure_change") and placeables(op["text"]) != placeables(before[r]):
                raise PatchError(f"{table}#{r}: structure changed {placeables(before[r])} -> "
                                 f"{placeables(op['text'])} (colour spans/speakers/speeches must be kept; "
                                 "set allow_structure_change = true only with review)")
            t.set(r, op["text"])
            if t.text(r) != op["text"] and t.text(r) != op["text"].replace("\n", "{br}"):
                raise PatchError(f"{table}#{r}: text does not round-trip: {t.text(r)!r}")
            m = t.width(r)
            if "budget" in op:
                if m is None:
                    raise PatchError(f"{table}#{r}: budget given but no TNF font resolved")
                if m.max_width > op["budget"]:
                    raise PatchError(f"{table}#{r}: line widths {m.widths} exceed budget {op['budget']}")
            report.append({"op": "text", "table": t.gsm_entry.name, "gsm_index": t.gsm_entry.index,
                           "fim_index": t.fim_entry.index if t.fim_entry else None, "record": r,
                           "grammar": t.grammar_name, "before": before[r], "after": t.text(r),
                           "line_widths": list(m.widths) if m else None, "budget": op.get("budget")})
        for i, b in t.build().items():
            if i in replacements:
                raise PatchError(f"member {i} edited by two operation groups")
            replacements[i] = b
    return replacements


def _texture_ops(archive: arcmod.Archive, ops: list[dict], base: Path, report: list) -> dict[int, bytes]:
    import numpy as np
    from PIL import Image
    from . import xet
    out = {}
    for op in ops:
        e = archive.find(op["member"], magic=xet.MAGIC) if isinstance(op["member"], str) else archive[op["member"]]
        cand_path = base / op["candidate"]
        cand_bytes = cand_path.read_bytes()
        if "candidate_sha256" not in op:
            raise PatchError(f"{op['member']}: candidate_sha256 (approval binding) is required")
        if sha256(cand_bytes) != op["candidate_sha256"]:
            raise PatchError(f"{op['member']}: candidate changed since approval "
                             f"({sha256(cand_bytes)} != {op['candidate_sha256']})")
        cand = np.array(Image.open(cand_path).convert("RGBA"))
        mask = np.array(Image.open(base / op["mask"]).convert("L")) > 127 if op.get("mask") else None
        colour = tuple(op["prefill_colour"]) if op.get("prefill_colour") else None
        new, rep = xet.graft(e.raw, cand, mask=mask, prefill=op.get("prefill", "dilate"),
                             prefill_colour=colour, allow_inconclusive_byte_order=op.get("allow_inconclusive", False))
        if e.index in out:
            raise PatchError(f"member {e.index} edited twice")
        out[e.index] = new
        report.append({"op": "texture", "member": e.name, "index": e.index,
                       "candidate_sha256": op["candidate_sha256"], "graft": json.loads(rep.to_json())})
    return out


def _member_ops(archive: arcmod.Archive, ops: list[dict], base: Path, report: list) -> dict[int, bytes]:
    out = {}
    for op in ops:
        e = archive.find(op["member"]) if isinstance(op["member"], str) else archive[op["member"]]
        data = (base / op["source"]).read_bytes()
        if sha256(data) != op.get("source_sha256"):
            raise PatchError(f"member {e.index}: source hash mismatch or missing source_sha256")
        if data[:4] != e.magic:
            raise PatchError(f"member {e.index}: replacement magic {data[:4]!r} != {e.magic!r}")
        out[e.index] = data
        report.append({"op": "member", "member": e.name, "index": e.index,
                       "before_sha256": sha256(e.raw), "after_sha256": sha256(data)})
    return out


def build(patchset_path: Path, root: Path, out_dir: Path) -> dict:
    """Build every archive of a patchset from the live root into out_dir."""
    patchset_path = Path(patchset_path).resolve()
    spec = load(patchset_path)
    base = patchset_path.parent
    root, out_dir = Path(root), Path(out_dir)
    if out_dir.resolve() == root.resolve() or root.resolve() in out_dir.resolve().parents:
        raise PatchError("build output must be outside the live root")
    record = {"schema": BUILD_SCHEMA, "patchset_id": spec["id"], "patchset_sha256": file_sha256(patchset_path),
              "tool": f"basara {__version__}", "built_utc": _now(), "archives": []}
    for a in spec.get("archive", []):
        src = root / a["path"]
        data = src.read_bytes()
        if sha256(data) != a["sha256"]:
            raise PatchError(f"{a['path']}: live sha256 {sha256(data)} != patchset {a['sha256']} "
                             "(re-author the patchset against the current bytes)")
        archive = arcmod.read(data)
        ops: list = []
        repl: dict[int, bytes] = {}
        for part in (_text_ops(archive, a.get("text", []), ops),
                     _texture_ops(archive, a.get("texture", []), base, ops) if a.get("texture") else {},
                     _member_ops(archive, a.get("member", []), base, ops)):
            clash = set(part) & set(repl)
            if clash:
                raise PatchError(f"{a['path']}: members {sorted(clash)} edited by more than one operation")
            repl.update(part)
        out = arcmod.rebuild(data, repl)
        verify = arcmod.verify_rebuild(data, out, repl)
        _post_verify(out, a, ops)
        dest = out_dir / a["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(out)
        record["archives"].append({"path": a["path"], "input_sha256": sha256(data), "output_sha256": sha256(out),
                                   "changed_members": sorted(repl), "operations": ops, "arc_verify": verify})
    _lockstep_check(record)
    (out_dir / "build.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def _post_verify(out: bytes, a: dict, ops: list) -> None:
    """Re-open the FINISHED archive and re-read every edited table."""
    archive = arcmod.read(out)
    tables = {}
    for op in ops:
        if op["op"] != "text":
            continue
        t = tables.get(op["gsm_index"])
        if t is None:
            t = tables[op["gsm_index"]] = MessageTable.open(archive, op["gsm_index"], grammar=op["grammar"])
        if t.text(op["record"]) != op["after"]:
            raise PatchError(f"{a['path']}: record {op['record']} re-reads as {t.text(op['record'])!r}")
    from .msg import check
    for t in tables.values():
        if t.fim is not None:
            rep = check(t.gsm, t.fim, t.grammar_name)
            if not rep.ok:
                raise PatchError(f"{a['path']}: finished table violates the FIM contract: {rep.violations[:3]}")


def _lockstep_check(record: dict) -> None:
    """The same texture candidate applied to several archives must produce
    byte-identical members (co-resident duplicate providers)."""
    seen: dict[tuple, str] = {}
    for a in record["archives"]:
        for op in a["operations"]:
            if op["op"] == "texture":
                key = (op["member"].lower(), op["candidate_sha256"])
                h = op["graft"]["output_sha256"]
                if seen.setdefault(key, h) != h:
                    raise PatchError(f"lockstep providers of {op['member']} diverge after graft")


# ---------------------------------------------------------------- install
def _atomic_write(dest: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def install(build_dir: Path, root: Path, backup_root: Path, *, dry_run: bool = False) -> dict:
    build_dir, root, backup_root = Path(build_dir), Path(root), Path(backup_root)
    rec = json.loads((build_dir / "build.json").read_text(encoding="utf-8"))
    if rec.get("schema") != BUILD_SCHEMA:
        raise PatchError("not a basara build directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = backup_root / f"{rec['patchset_id']}_{stamp}"
    plan = []
    for a in rec["archives"]:
        live = root / a["path"]
        built = (build_dir / a["path"]).read_bytes()
        if sha256(built) != a["output_sha256"]:
            raise PatchError(f"{a['path']}: build output was modified after build")
        cur = file_sha256(live)
        if cur == a["output_sha256"]:
            plan.append((a, live, built, "already-installed"))
        elif cur == a["input_sha256"]:
            plan.append((a, live, built, "install"))
        else:
            raise PatchError(f"{a['path']}: live bytes {cur} are neither the build input nor output "
                             "-- someone changed the file; rebuild against current bytes")
    result = {"schema": INSTALL_SCHEMA, "patchset_id": rec["patchset_id"], "build_patchset_sha256": rec["patchset_sha256"],
              "installed_utc": _now(), "root": str(root), "backup_dir": str(bdir), "dry_run": dry_run, "archives": []}
    if dry_run:
        result["archives"] = [{"path": a["path"], "action": act} for a, _, _, act in plan]
        return result
    todo = [p for p in plan if p[3] == "install"]
    if not todo:
        result["backup_dir"] = None
        result["archives"] = [{"path": a["path"], "action": act} for a, _, _, act in plan]
        return result
    n = 1
    while bdir.exists():                   # never reuse or overwrite a backup folder
        n += 1
        bdir = backup_root / f"{rec['patchset_id']}_{stamp}_{n}"
    result["backup_dir"] = str(bdir)
    bdir.mkdir(parents=True)
    sums = []
    for a, live, _, _ in todo:  # 1. back up EVERYTHING first; verify each backup from disk
        dst = bdir / a["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(live.read_bytes())
        if file_sha256(dst) != a["input_sha256"]:
            raise PatchError(f"{a['path']}: backup read-back hash mismatch; nothing installed")
        sums.append(f"{a['input_sha256']}  {a['path']}")
    (bdir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    for a, live, built, act in plan:  # 2. guarded atomic replace + read-back
        if act == "install":
            if file_sha256(live) != a["input_sha256"]:
                raise PatchError(f"{a['path']}: live changed during install; stopping (backups kept in {bdir})")
            _atomic_write(live, built)
            if file_sha256(live) != a["output_sha256"]:
                raise PatchError(f"{a['path']}: read-back mismatch after install (backup: {bdir / a['path']})")
        result["archives"].append({"path": a["path"], "action": act, "before_sha256": a["input_sha256"],
                                   "after_sha256": a["output_sha256"],
                                   "backup": str(bdir / a["path"]) if act == "install" else None})
    (bdir / "INSTALL_RECORD.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def rollback(install_record: Path, *, dry_run: bool = False) -> dict:
    rec = json.loads(Path(install_record).read_text(encoding="utf-8"))
    if rec.get("schema") != INSTALL_SCHEMA:
        raise PatchError("not a basara install record")
    root = Path(rec["root"])
    out = {"patchset_id": rec["patchset_id"], "archives": []}
    for a in rec["archives"]:
        if a["action"] != "install":
            continue
        live = root / a["path"]
        cur = file_sha256(live)
        if cur == a["before_sha256"]:
            act = "already-rolled-back"
        elif cur == a["after_sha256"]:
            act = "restore"
            backup = Path(a["backup"]).read_bytes()
            if sha256(backup) != a["before_sha256"]:
                raise PatchError(f"{a['path']}: backup is corrupt")
            if not dry_run:
                _atomic_write(live, backup)
                if file_sha256(live) != a["before_sha256"]:
                    raise PatchError(f"{a['path']}: read-back mismatch after rollback")
        else:
            raise PatchError(f"{a['path']}: live bytes changed after install ({cur}); refusing to erase later edits")
        out["archives"].append({"path": a["path"], "action": act})
    return out
