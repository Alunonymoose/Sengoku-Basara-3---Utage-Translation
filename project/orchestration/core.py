from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Iterable

SNAPSHOT_SCHEMA = "BASARA_FOUNDRY_LIVE_SNAPSHOT_V1"
RECIPE_SCHEMA = "BASARA_FOUNDRY_PATCH_RECIPE_V1"
SCHEMA_VERSION = 1


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "project/tools/donor_matcher_v5_1_2026-09-23/safe_arc.py").is_file():
            return p
    raise RuntimeError("Could not locate repository root containing pinned safe_arc.py")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_safe_arc(repo_root: Path):
    return load_module(repo_root / "project/tools/donor_matcher_v5_1_2026-09-23/safe_arc.py", "foundry_safe_arc")


def load_ownership_module(repo_root: Path):
    return load_module(repo_root / "project/tools/resource_ownership_2026-09-23/basara_resource_ownership.py", "foundry_resource_ownership")


def canonical_internal_path(name: str) -> str:
    name = name.replace("/", "\\")
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in name)


def canonical_scan_root(user_root: Path) -> tuple[Path, Path]:
    root = user_root.resolve()
    return ((root / "PS3_GAME", root) if (root / "PS3_GAME").is_dir() else (root, root))


def iter_files(scan_root: Path, state_root: Path) -> Iterable[Path]:
    state_root = state_root.resolve()
    for dirpath, dirnames, filenames in os.walk(scan_root):
        d = Path(dirpath)
        dirnames[:] = [name for name in dirnames if name != ".foundry" and not ((d / name).resolve() == state_root or state_root in (d / name).resolve().parents)]
        for name in filenames:
            yield d / name


def tree_hash(records: list[dict]) -> str:
    h = hashlib.sha256()
    for rec in sorted(records, key=lambda x: x["path"]):
        h.update(rec["path"].encode("utf-8")); h.update(b"\0")
        h.update(str(rec["size"]).encode("ascii")); h.update(b"\0")
        h.update(bytes.fromhex(rec["sha256"])); h.update(b"\n")
    return h.hexdigest()
