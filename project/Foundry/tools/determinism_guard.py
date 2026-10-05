from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

DEFAULT_IGNORES = {".git", "__pycache__", ".DS_Store", "Thumbs.db"}


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def should_ignore(rel: Path, ignores: set[str]) -> bool:
    return any(part in ignores for part in rel.parts)


def tree_manifest(root: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> dict[str, dict]:
    root = root.resolve()
    ignore_set = set(ignores)
    out: dict[str, dict] = {}
    if root.is_file():
        return {
            root.name: {
                "size": root.stat().st_size,
                "sha256": sha256_file(root),
            }
        }
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = p.relative_to(root)
        if should_ignore(rel, ignore_set):
            continue
        out[rel.as_posix()] = {
            "size": p.stat().st_size,
            "sha256": sha256_file(p),
        }
    return out


def compare_manifests(left: dict[str, dict], right: dict[str, dict]) -> dict:
    lkeys = set(left)
    rkeys = set(right)
    only_left = sorted(lkeys - rkeys)
    only_right = sorted(rkeys - lkeys)
    changed = []
    identical = 0
    for key in sorted(lkeys & rkeys):
        a = left[key]
        b = right[key]
        if a.get("size") == b.get("size") and a.get("sha256") == b.get("sha256"):
            identical += 1
        else:
            changed.append({
                "path": key,
                "left": a,
                "right": b,
            })
    return {
        "identical_files": identical,
        "changed_files": changed,
        "only_left": only_left,
        "only_right": only_right,
        "reproducible": not changed and not only_left and not only_right,
    }


def compare_trees(left_root: Path, right_root: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> dict:
    left = tree_manifest(left_root, ignores)
    right = tree_manifest(right_root, ignores)
    result = compare_manifests(left, right)
    result.update({
        "left": str(left_root),
        "right": str(right_root),
        "left_file_count": len(left),
        "right_file_count": len(right),
    })
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare two build/output trees byte-for-byte for reproducibility"
    )
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("--ignore", action="append", default=[])
    ap.add_argument("--output")
    args = ap.parse_args()
    ignores = set(DEFAULT_IGNORES) | set(args.ignore)
    result = compare_trees(Path(args.left), Path(args.right), ignores)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["reproducible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
