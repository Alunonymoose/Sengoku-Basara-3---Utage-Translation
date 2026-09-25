"""basara -- one command-line tool for the Utage English patch.

  basara arc ls <file.arc> [--json]                 list members (no inflation)
  basara arc x <file.arc> <member> -o <out>         extract one member
  basara msg tables <file.arc>                      GSM/FIM pairs, grammar, contract status
  basara msg show <file.arc> <table> [-r N ...]     records as editable markup (+ widths)
  basara msg census <rom/eng> [--out f.json]        contract + grammar over the whole tree
  basara tex <cmd> ...                              texture commands (basara tex -h)
  basara catalog export <arc> <table> -o f.tsv [--ref jpn.arc]
  basara catalog lint <f.tsv> --arc <arc> --table <t> [--budget N] [--terms terms.json]
  basara catalog import <f.tsv> --arc <arc> --table <t> --arc-path <rel> --id <id> -o patch.toml
  basara build <patchset.toml> --root <rom/eng> --out <dir>
  basara install <build-dir> --root <rom/eng> --backup-root <dir> [--dry-run]
  basara rollback <INSTALL_RECORD.json> [--dry-run]

Nothing writes into the live root except `install`/`rollback`, and those
back up first, guard every write by hash, and read back what they wrote.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import arc as arcmod
from . import catalog as cat
from . import patch as patchmod
from .font import CSA_MAGIC, TNF_MAGIC
from .mthash import label
from .msg import FIM_MAGIC, GSM_MAGIC, Fim, Gsm, MsgError, check, detect_grammar
from .table import FontRef, MessageTable


def _load(path: str) -> arcmod.Archive:
    data = Path(path).read_bytes()
    try:
        return arcmod.read(data)
    except arcmod.ArcError:
        return arcmod.inspect(data)


def _font(a) -> FontRef | None:
    return FontRef(a.tnf, a.csa) if (a.tnf is not None or a.csa is not None) else None


def _table(a) -> MessageTable:
    key = int(a.table) if str(a.table).isdigit() else a.table
    return MessageTable.open(_load(a.arc), key, font=_font(a))


# ------------------------------------------------------------------ arc
def cmd_arc_ls(a):
    arc = _load(a.arc)
    if a.json:
        print(json.dumps({"sha256": arc.sha256, "strict": arc.strict, "anomalies": list(arc.anomalies),
                          "members": [e.summary() | {"magic": e.magic.hex()} for e in arc]}, indent=2))
        return
    print(f"{a.arc}  {len(arc)} members  sha256={arc.sha256}  align={arc.alignment}"
          + ("" if arc.strict else f"  READ-ONLY: {'; '.join(arc.anomalies)}"))
    for e in arc:
        mg = e.magic.replace(b"\0", b".").decode("latin-1")
        print(f"{e.index:4} {mg:5} {e.raw_size:9} {label(e.type_hash):>11}  {e.name}")


def cmd_arc_x(a):
    e = _load(a.arc).find(int(a.member) if a.member.isdigit() else a.member)
    Path(a.out).write_bytes(e.raw)
    print(f"{e.name} -> {a.out} ({len(e.raw)} bytes)")


# ------------------------------------------------------------------ msg
def _pairs(arc: arcmod.Archive):
    for e in arc:
        if e.magic == GSM_MAGIC:
            yield e, arc.pair(e, FIM_MAGIC)


def _table_status(g, f) -> dict:
    gsm = Gsm.parse(g.raw)
    row = {"gsm": g.index, "fim": f.index if f else None, "name": g.name, "records": len(gsm)}
    if f is None:
        row["status"] = "NO_FIM"
        return row
    fim = Fim.parse(f.raw)
    try:
        grammar = detect_grammar(gsm, fim)
        rep = check(gsm, fim, grammar)
        row.update(status="OK", grammar=grammar, rows=rep.rows, ambiguous_words=rep.ambiguous_words)
    except MsgError as exc:
        row.update(status="UNCHARTED", detail=str(exc)[:300])
    return row


def cmd_msg_tables(a):
    arc = _load(a.arc)
    for g, f in _pairs(arc):
        r = _table_status(g, f)
        extra = f"grammar={r.get('grammar')}" if r["status"] == "OK" else r.get("detail", "")
        print(f"gsm {r['gsm']:4} fim {str(r['fim']):>4} {r['records']:6} rec  {r['status']:10} {extra}  {r['name']}")
    fonts = [e.index for e in arc.by_magic(TNF_MAGIC)], [e.index for e in arc.by_magic(CSA_MAGIC)]
    print(f"fonts: TNF {fonts[0]}  CSA {fonts[1]}")


def cmd_msg_show(a):
    t = _table(a)
    records = a.record or range(len(t))
    print(f"# {t.gsm_entry.name}  grammar={t.grammar_name}  records={len(t)}"
          + ("" if t.csa else "  (no CSA resolved: glyphs shown as {g:})"))
    for r in records:
        m = t.width(r)
        w = f"  [{'/'.join(map(str, m.widths))}]" if m else ""
        print(f"{r:5}{w}  {t.text(r)}")


def cmd_msg_census(a):
    root = Path(a.root)
    out = {"tool": f"basara {__version__}", "root": str(root), "tables": [], "archive_errors": []}
    for p in sorted(root.rglob("*.arc")):
        try:
            arc = _load(str(p))
            for g, f in _pairs(arc):
                out["tables"].append({"arc": str(p.relative_to(root))} | _table_status(g, f))
        except Exception as exc:  # read-only census: record and continue
            out["archive_errors"].append({"arc": str(p.relative_to(root)), "error": repr(exc)})
    counts: dict[str, int] = {}
    for t in out["tables"]:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    out["summary"] = counts
    text = json.dumps(out, indent=2)
    if a.out:
        Path(a.out).write_text(text)
    print(json.dumps(counts) if a.out else text)


# -------------------------------------------------------------- catalog
def cmd_cat_export(a):
    t = _table(a)
    ref = MessageTable.open(_load(a.ref), t.gsm_entry.name) if a.ref else None
    Path(a.out).write_text(cat.export(t, ref, only_nonempty=not a.all), encoding="utf-8")
    print(f"wrote {a.out}")


def cmd_cat_lint(a):
    rows = cat.read(Path(a.catalog))
    findings = cat.lint(rows, _table(a), budget=a.budget, terms_path=Path(a.terms) if a.terms else None)
    for f in findings:
        print(f)
    errors = sum(f.level == "ERROR" for f in findings)
    print(f"{len(rows)} rows, {errors} errors, {len(findings) - errors} warnings")
    return 1 if errors else 0


def cmd_cat_import(a):
    rows = cat.read(Path(a.catalog))
    t = _table(a)
    errs = [f for f in cat.lint(rows, t, budget=a.budget) if f.level == "ERROR"]
    if errs:
        for f in errs:
            print(f)
        sys.exit("catalog has lint errors; nothing written")
    toml = cat.to_patchset(rows, patch_id=a.id, arc_path=a.arc_path, arc_sha256=t.archive.sha256,
                           table=t.gsm_entry.name, budget=a.budget)
    Path(a.out).write_text(toml, encoding="utf-8")
    print(f"wrote {a.out}")


# ---------------------------------------------------------------- patch
def cmd_build(a):
    rec = patchmod.build(Path(a.patchset), Path(a.root), Path(a.out))
    for x in rec["archives"]:
        print(f"{x['path']}: {x['input_sha256'][:12]} -> {x['output_sha256'][:12]}  "
              f"members {x['changed_members']}  ops {len(x['operations'])}")
    print(f"build record: {Path(a.out) / 'build.json'}")


def cmd_install(a):
    rec = patchmod.install(Path(a.build), Path(a.root), Path(a.backup_root), dry_run=a.dry_run)
    print(json.dumps(rec, indent=2))


def cmd_rollback(a):
    print(json.dumps(patchmod.rollback(Path(a.record), dry_run=a.dry_run), indent=2))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["tex"]:
        from . import texcli
        texcli.main(argv[1:])
        return 0
    p = argparse.ArgumentParser(prog="basara", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"basara {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    def font_args(s):
        s.add_argument("--tnf", type=int, help="explicit TNF member index")
        s.add_argument("--csa", type=int, help="explicit CSA member index")

    g = sub.add_parser("arc").add_subparsers(dest="cmd", required=True)
    s = g.add_parser("ls"); s.add_argument("arc"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_arc_ls)
    s = g.add_parser("x"); s.add_argument("arc"); s.add_argument("member"); s.add_argument("-o", "--out", required=True); s.set_defaults(fn=cmd_arc_x)

    g = sub.add_parser("msg").add_subparsers(dest="cmd", required=True)
    s = g.add_parser("tables"); s.add_argument("arc"); s.set_defaults(fn=cmd_msg_tables)
    s = g.add_parser("show"); s.add_argument("arc"); s.add_argument("table"); s.add_argument("-r", "--record", type=int, action="append"); font_args(s); s.set_defaults(fn=cmd_msg_show)
    s = g.add_parser("census"); s.add_argument("root"); s.add_argument("--out"); s.set_defaults(fn=cmd_msg_census)

    g = sub.add_parser("catalog").add_subparsers(dest="cmd", required=True)
    s = g.add_parser("export"); s.add_argument("arc"); s.add_argument("table"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--ref", help="reference archive (e.g. rom/jpn) for the `reference` column"); s.add_argument("--all", action="store_true"); font_args(s); s.set_defaults(fn=cmd_cat_export)
    s = g.add_parser("lint"); s.add_argument("catalog"); s.add_argument("--arc", required=True); s.add_argument("--table", required=True)
    s.add_argument("--budget", type=int); s.add_argument("--terms"); font_args(s); s.set_defaults(fn=cmd_cat_lint)
    s = g.add_parser("import"); s.add_argument("catalog"); s.add_argument("--arc", required=True); s.add_argument("--table", required=True)
    s.add_argument("--arc-path", required=True, help="archive path relative to rom/eng"); s.add_argument("--id", required=True)
    s.add_argument("--budget", type=int); s.add_argument("-o", "--out", required=True); font_args(s); s.set_defaults(fn=cmd_cat_import)

    s = sub.add_parser("build"); s.add_argument("patchset"); s.add_argument("--root", required=True); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_build)
    s = sub.add_parser("install"); s.add_argument("build"); s.add_argument("--root", required=True); s.add_argument("--backup-root", required=True)
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("rollback"); s.add_argument("record"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_rollback)

    a = p.parse_args(argv)
    try:
        return a.fn(a) or 0
    except (arcmod.ArcError, MsgError, patchmod.PatchError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
