from __future__ import annotations
import hashlib
from pathlib import Path

def equivalent_sha256(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    out = {"raw": hashlib.sha256(data).hexdigest()}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return out
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    out["utf8_lf"] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    out["utf8_crlf"] = hashlib.sha256(normalized.replace("\n", "\r\n").encode("utf-8")).hexdigest()
    return out

def require_hash(path: Path, expected: str) -> str:
    if not path.is_file():
        raise RuntimeError(f"missing dependency: {path}")
    candidates = equivalent_sha256(path)
    for form, digest in candidates.items():
        if digest == expected:
            return form
    raise RuntimeError(
        f"dependency hash drift: {path} expected={expected} candidates={sorted(candidates.items())}"
    )
