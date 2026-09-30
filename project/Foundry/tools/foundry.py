from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(HERE))

import foundry_graph as fg
import texture_triage as tq


def print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def graph_for(live_root: Path):
    return fg.FoundryGraph(fg.default_db(live_root), live_root)


def show_arc(arc: str) -> int:
    tool = PROJECT / "tools" / "arc_texture_gallery.py"
    if not tool.exists():
        raise FileNotFoundError(tool)
    proc = subprocess.run([sys.executable, str(tool), arc], text=True)
    if proc.returncode:
        return proc.returncode
    latest = Path(r"E:\BASARA_WORK\ARC_TEXTURE_GALLERIES\LATEST.json")
    if latest.exists():
        data = json.loads(latest.read_text(encoding="utf-8"))
        manifest_path = Path(data["manifest"]) if data.get("manifest") else None
        texture_count = None
        if manifest_path and manifest_path.exists():
            texture_count = json.loads(manifest_path.read_text(encoding="utf-8")).get("texture_count")
        print_json({
            "arc": data.get("arc"),
            "texture_count": texture_count,
            "pdf": data.get("texture_book_pdf"),
            "manifest": data.get("manifest"),
            "output_dir": data.get("output_dir"),
        })
    return 0


def why(graph: fg.FoundryGraph, pattern: str):
    rows = graph.query(pattern, 250)
    owner_rows = graph.owners(pattern, 250)
    by_sha = {}
    for row in owner_rows:
        by_sha.setdefault(row["raw_sha256"], []).append(row)
    print_json({
        "pattern": pattern,
        "matches": rows,
        "owners": owner_rows,
        "payload_groups": [
            {"raw_sha256": sha, "owners": owners}
            for sha, owners in by_sha.items()
        ],
    })


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="foundry",
        description="Single front door for BASARA Foundry live project intelligence"
    )
    ap.add_argument("--live-root", default=str(fg.DEFAULT_LIVE_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="rebuild/update the live Foundry Graph")
    b.add_argument("--no-jpn", action="store_true")
    b.add_argument("--no-sh", action="store_true")
    b.add_argument("--verbose", action="store_true")

    sub.add_parser("status", help="show graph and sign-off health")

    q = sub.add_parser("query", help="search live indexed resources")
    q.add_argument("pattern")
    q.add_argument("--limit", type=int, default=100)

    o = sub.add_parser("owners", help="show every indexed owner/provider")
    o.add_argument("name")

    w = sub.add_parser("why", help="resource identity + owner/payload explanation")
    w.add_argument("pattern")

    s = sub.add_parser("suspects", help="texture candidates needing visual review")
    s.add_argument("--limit", type=int, default=250)

    a = sub.add_parser("audit", help="export whole-tree texture QA priority queue")
    a.add_argument("--include-signed", action="store_true")
    a.add_argument("--limit", type=int, default=5000)
    a.add_argument("--top", type=int, default=30)

    oa = sub.add_parser("ocr-audit", help="OCR high-risk texture candidates for visible Japanese")
    oa.add_argument("--limit", type=int, default=200)
    oa.add_argument("--min-score", type=int, default=30)

    c = sub.add_parser("certify", help="hash-certify a live folder/file")
    c.add_argument("scope")
    c.add_argument("--name", required=True)
    c.add_argument("--rule-version", default="texture-qa-v1")

    sub.add_parser("signoffs", help="re-evaluate all machine-readable signoffs")
    sub.add_parser("runtime-bind", help="bind runtime acceptance matrix to exact current graph fingerprint")
    sub.add_parser("runtime-status", help="validate the current runtime acceptance matrix")

    rr = sub.add_parser("runtime-record", help="record hash-bound runtime evidence for one acceptance row")
    rr.add_argument("row_id")
    rr.add_argument("status", choices=["PASS", "FAIL", "BLOCKED", "NOT_TESTED"])
    rr.add_argument("evidence", nargs="*")
    rr.add_argument("--note")

    d = sub.add_parser("doctor", help="run the whole-project health gate")
    d.add_argument("--strict", action="store_true")

    dash = sub.add_parser("dashboard", help="build the one-screen live project dashboard")
    dash.add_argument("--refresh", action="store_true")
    dash.add_argument("--top", type=int, default=12)

    orc = sub.add_parser("oracles", help="validate pinned external oracles and optionally check upstream drift")
    orc.add_argument("--online", action="store_true")

    nx = sub.add_parser("next", help="rank the next highest-value unsigned project folders")
    nx.add_argument("--limit", type=int, default=15)
    nx.add_argument("--mode", choices=["closeout", "risk", "smallest"], default="closeout")

    imp = sub.add_parser("impact", help="show sign-off and duplicate-owner impact before mutating files")
    imp.add_argument("targets", nargs="+")
    imp.add_argument("--detail-limit", type=int, default=12)

    dtree = sub.add_parser("compare-trees", help="byte-compare two build/output trees for reproducibility")
    dtree.add_argument("left")
    dtree.add_argument("right")
    dtree.add_argument("--ignore", action="append", default=[])

    tm = sub.add_parser("tm", help="provenance-aware translation memory (add/find/audit/import/export)")
    tm.add_argument("tm_args", nargs=argparse.REMAINDER)

    sh = sub.add_parser("show", help="generate the numbered texture-book PDF for an ARC")
    sh.add_argument("arc")

    args = ap.parse_args()
    live_root = Path(args.live_root)

    if args.cmd == "build":
        print_json(fg.build_graph(
            live_root, include_jpn=not args.no_jpn,
            include_sh=not args.no_sh, verbose=args.verbose
        ))
        return 0
    if args.cmd == "show":
        return show_arc(args.arc)
    if args.cmd == "ocr-audit":
        tool = HERE / "texture_ocr_triage.py"
        return subprocess.run([
            sys.executable, str(tool),
            "--limit", str(args.limit),
            "--min-score", str(args.min_score),
        ]).returncode
    if args.cmd == "runtime-bind":
        tool = HERE / "runtime_bind.py"
        return subprocess.run([sys.executable, str(tool), "--live-root", str(live_root)]).returncode
    if args.cmd == "runtime-status":
        matrix = live_root / ".foundry" / "runtime" / "RUNTIME_ACCEPTANCE_CURRENT.json"
        validator = PROJECT / "runtime" / "validate_runtime_matrix.py"
        return subprocess.run([sys.executable, str(validator), str(matrix)]).returncode
    if args.cmd == "runtime-record":
        tool = HERE / "runtime_record.py"
        cmd = [
            sys.executable, str(tool),
            args.row_id, args.status, *args.evidence,
            "--live-root", str(live_root),
        ]
        if args.note:
            cmd.extend(["--note", args.note])
        return subprocess.run(cmd).returncode
    if args.cmd == "doctor":
        tool = HERE / "doctor.py"
        cmd = [sys.executable, str(tool), "--live-root", str(live_root)]
        if args.strict:
            cmd.append("--strict")
        return subprocess.run(cmd).returncode
    if args.cmd == "dashboard":
        tool = HERE / "dashboard.py"
        cmd = [
            sys.executable, str(tool),
            "--live-root", str(live_root),
            "--top", str(args.top),
        ]
        if args.refresh:
            cmd.append("--refresh")
        return subprocess.run(cmd).returncode
    if args.cmd == "oracles":
        tool = HERE / "oracle_audit.py"
        cmd = [sys.executable, str(tool)]
        if args.online:
            cmd.append("--online")
        return subprocess.run(cmd).returncode
    if args.cmd == "next":
        tool = HERE / "next_work.py"
        return subprocess.run([
            sys.executable, str(tool),
            "--db", str(fg.default_db(live_root)),
            "--limit", str(args.limit),
            "--mode", args.mode,
        ]).returncode
    if args.cmd == "impact":
        tool = HERE / "change_impact.py"
        return subprocess.run([
            sys.executable, str(tool),
            *args.targets,
            "--live-root", str(live_root),
            "--db", str(fg.default_db(live_root)),
            "--detail-limit", str(args.detail_limit),
        ]).returncode
    if args.cmd == "compare-trees":
        tool = HERE / "determinism_guard.py"
        cmd = [sys.executable, str(tool), args.left, args.right]
        for value in args.ignore:
            cmd.extend(["--ignore", value])
        return subprocess.run(cmd).returncode
    if args.cmd == "tm":
        tool = HERE / "translation_memory.py"
        db = live_root / ".foundry" / "cache" / "translation_memory.sqlite"
        return subprocess.run([
            sys.executable, str(tool), "--db", str(db), *args.tm_args
        ]).returncode

    graph = graph_for(live_root)
    try:
        if args.cmd == "status":
            print_json(graph.summary())
        elif args.cmd == "query":
            print_json(graph.query(args.pattern, args.limit))
        elif args.cmd == "owners":
            print_json(graph.owners(args.name))
        elif args.cmd == "why":
            why(graph, args.pattern)
        elif args.cmd == "suspects":
            print_json(graph.texture_suspects(args.limit))
        elif args.cmd == "audit":
            result = tq.build_queue(fg.default_db(live_root), args.include_signed, args.limit)
            out = live_root / ".foundry" / "TEXTURE_TRIAGE.json"
            jp, cp = tq.export(result, out)
            print_json({
                "candidate_count": result["candidate_count"],
                "arc_count": result["arc_count"],
                "top_folders": result["top_folders"][:args.top],
                "top_arcs": result["top_arcs"][:args.top],
                "json": str(jp),
                "csv": str(cp),
            })
        elif args.cmd == "certify":
            cert = graph.create_signoff(args.scope, args.name, args.rule_version)
            print_json({"certificate": str(cert), "signoffs": graph.evaluate_signoffs()})
        elif args.cmd == "signoffs":
            print_json(graph.evaluate_signoffs())
    finally:
        graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
