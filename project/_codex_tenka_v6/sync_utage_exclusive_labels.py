from __future__ import annotations

"""Synchronize finished Utage-exclusive character labels across English ARCs."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arc_tools  # noqa: E402

ROOT = Path(r"E:\Utage Patching New")
ENG = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng"
RESULT = ENG / "result"
OUT = ROOT / r"_codex_tenka_v6\outside_result_sync"
TARGET_IDS = set(range(16, 30))
ID_RE = re.compile(r"_(\d{3})_ID_HQ$", re.IGNORECASE)


def target_kind(name: str) -> tuple[int, str] | None:
    lowered = name.lower()
    match = ID_RE.search(name)
    if not match:
        return None
    number = int(match.group(1))
    if number not in TARGET_IDS:
        return None
    if "charasele_02" in lowered:
        return number, "wide"
    if any(token in lowered for token in ("\\name\\name_", "\\teki_name\\", "\\teki2_name\\")):
        return number, "small"
    return None


def source_resources() -> dict[tuple[int, str], bytes]:
    resources = {}
    for number in TARGET_IDS:
        archive = arc_tools.parse_arc(RESULT / f"pl{number:03}.arc")
        resources[(number, "small")] = arc_tools.unpack(archive.entries[2])
        resources[(number, "wide")] = arc_tools.unpack(archive.entries[4])
    return resources


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = source_resources()
    report = {"status": "pass", "archives": [], "changed_resources": 0}
    for path in sorted(ENG.rglob("*.arc")):
        if path.is_relative_to(RESULT):
            continue
        archive = arc_tools.parse_arc(path)
        replacements: dict[int, bytes] = {}
        matches = []
        for entry in archive.entries:
            target = target_kind(entry.name)
            if target is None:
                continue
            number, kind = target
            replacement = sources[(number, kind)]
            if len(replacement) != entry.raw_size:
                raise ValueError(
                    f"{path}: entry {entry.index} size mismatch "
                    f"{len(replacement)} != {entry.raw_size}"
                )
            replacements[entry.index] = replacement
            matches.append(
                {"index": entry.index, "name": entry.name, "character": number, "kind": kind}
            )
        if not replacements:
            continue
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        for index, replacement in replacements.items():
            if arc_tools.unpack(verified.entries[index]) != replacement:
                raise AssertionError(f"verification mismatch: {path} entry {index}")
        report["archives"].append({"archive": str(path), "resources": matches})
        report["changed_resources"] += len(replacements)
    report["archive_count"] = len(report["archives"])
    report["source_result_archives"] = 14
    (OUT / "OUTSIDE_RESULT_SYNC_REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "status": "pass",
        "archives": report["archive_count"],
        "resources": report["changed_resources"],
        "report": str(OUT / "OUTSIDE_RESULT_SYNC_REPORT.json"),
    }))


if __name__ == "__main__":
    main()
