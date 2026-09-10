"""Safe discovery of Alrummi 3 extension manifests.

Discovery is deliberately manifest-only.  An update from another AI is shown
to the user first and is not imported or executed automatically.  A future
release can add an explicit "enable extension" action after its files have
been reviewed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtensionInfo:
    extension_id: str
    name: str
    version: str
    api_version: str
    source: Path
    capabilities: tuple[str, ...]
    description: str
    status: str


def _read_manifest(path: Path) -> ExtensionInfo:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("id", "name", "version", "api_version")
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise ValueError(f"manifest missing {', '.join(missing)}")
    capabilities = tuple(str(item) for item in data.get("capabilities", []))
    return ExtensionInfo(
        extension_id=str(data["id"]),
        name=str(data["name"]),
        version=str(data["version"]),
        api_version=str(data["api_version"]),
        source=path,
        capabilities=capabilities,
        description=str(data.get("description", "")),
        status="compatible" if str(data["api_version"]) == "1.0" else "review required",
    )


def discover_extensions(root: Path) -> tuple[ExtensionInfo, ...]:
    """Return manifest information from built-ins and drop-in update folders."""

    search_roots = (root / "ai_extensions", root / "updates")
    found: list[ExtensionInfo] = []
    seen: set[str] = set()
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for manifest in sorted(search_root.rglob("manifest.json")):
            try:
                info = _read_manifest(manifest)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                continue
            if info.extension_id in seen:
                continue
            seen.add(info.extension_id)
            found.append(info)
    return tuple(found)

