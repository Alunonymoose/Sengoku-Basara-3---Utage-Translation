from __future__ import annotations
from pathlib import Path


def resolve_snapshot(path: str | Path) -> Path:
    p = Path(path).resolve()
    if p.is_file() and p.name == "index.sqlite3": return p
    if p.is_dir() and (p / "index.sqlite3").is_file(): return p / "index.sqlite3"
    if p.is_dir() and (p / ".foundry/CURRENT_SNAPSHOT").is_file():
        sid = (p / ".foundry/CURRENT_SNAPSHOT").read_text().strip()
        return p / ".foundry/snapshots" / sid / "index.sqlite3"
    if p.is_dir() and (p / "CURRENT_SNAPSHOT").is_file():
        sid = (p / "CURRENT_SNAPSHOT").read_text().strip()
        return p / "snapshots" / sid / "index.sqlite3"
    raise SystemExit(f"Cannot resolve snapshot database from {p}")
