from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

LIVE_ENG = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
DEFAULT_TRIAGE = Path(r"E:\Utage Patching New\.foundry\TEXTURE_TRIAGE.json")
DEFAULT_OUTPUT = Path(r"E:\Utage Patching New\.foundry\TEXTURE_OCR_TRIAGE.json")
PROJECT = Path(__file__).resolve().parents[2]
SAFE_ARC = PROJECT / r"tools\donor_matcher_v5_1_2026-09-23\safe_arc.py"
XET = PROJECT / r"texture_tools\xet_ps3_2026-09-25\xet_ps3.py"
ALRUMMI = PROJECT / "Alrummi3"

JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fffã€…ã€†ãƒµãƒ¶]")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def has_japanese(text: str) -> bool:
    return bool(JP_RE.search(text or ""))


def run(triage_path: Path, output: Path, limit: int = 200, min_score: int = 30) -> dict:
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    candidates = [
        t for t in triage.get("textures", [])
        if int(t.get("score", 0)) >= min_score
    ][:limit]

    sys.path.insert(0, str(ALRUMMI))
    import ocr as alrummi_ocr
    engine = alrummi_ocr.RapidEngine()
    safe_arc = load_module("foundry_ocr_safe_arc", SAFE_ARC)
    xet = load_module("foundry_ocr_xet", XET)

    grouped = defaultdict(list)
    for item in candidates:
        grouped[item["arc_path"]].append(item)

    hits = []
    checked = 0
    failures = []
    for arc_rel, items in grouped.items():
        arc = LIVE_ENG / Path(arc_rel)
        try:
            entries = safe_arc.parse_arc(arc.read_bytes())
        except Exception as exc:
            failures.append({"arc": arc_rel, "error": repr(exc)})
            continue
        for item in items:
            idx = int(item["member_index"])
            try:
                e = entries[idx]
                rgba = xet.decode_display(e["raw"])
                im = Image.fromarray(rgba, "RGBA")
                reads = engine.read_regions(im, scale=2)
                checked += 1
                jp = [
                    {
                        "text": r.text,
                        "confidence": r.confidence,
                        "box": list(r.box) if r.box else None,
                    }
                    for r in reads
                    if has_japanese(r.text)
                ]
                if jp:
                    hits.append({
                        "score": item["score"],
                        "arc_path": arc_rel,
                        "member_index": idx,
                        "name": item["name"],
                        "raw_sha256": item["raw_sha256"],
                        "ocr": jp,
                    })
            except Exception as exc:
                failures.append({
                    "arc": arc_rel,
                    "member_index": idx,
                    "name": item.get("name"),
                    "error": repr(exc),
                })

    result = {
        "schema": "BASARA_TEXTURE_OCR_TRIAGE_V1",
        "triage_source": str(triage_path),
        "candidate_limit": limit,
        "minimum_score": min_score,
        "checked": checked,
        "japanese_hit_count": len(hits),
        "hits": hits,
        "failures": failures,
        "policy": "OCR is triage evidence only and never authorizes automatic mutation.",
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR high-risk Foundry texture candidates for visible Japanese")
    ap.add_argument("--triage", default=str(DEFAULT_TRIAGE))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-score", type=int, default=30)
    args = ap.parse_args()
    result = run(Path(args.triage), Path(args.output), args.limit, args.min_score)
    print(json.dumps({
        "checked": result["checked"],
        "japanese_hit_count": result["japanese_hit_count"],
        "failure_count": len(result["failures"]),
        "output": args.output,
        "hits": result["hits"][:50],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
