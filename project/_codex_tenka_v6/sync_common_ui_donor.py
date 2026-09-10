from __future__ import annotations

"""Normalize the shared common_018 UI texture from the SH English donor."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arc_tools  # noqa: E402

ROOT = Path(r"E:\Utage Patching New")
ENG = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng"
SH_RESULT = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng\result_id.arc")
OUT = ROOT / r"_codex_tenka_v6\common_ui_sync"


def main() -> None:
    donor_archive = arc_tools.parse_arc(SH_RESULT)
    donor_entry = next(
        entry for entry in donor_archive.entries if "common_018_ID_HQ" in entry.name
    )
    donor = arc_tools.unpack(donor_entry)
    if len(donor) != donor_entry.raw_size:
        raise AssertionError("invalid donor raw size")

    report = {"status": "pass", "donor": str(SH_RESULT), "archives": [], "resources": 0}
    for path in sorted(ENG.rglob("*.arc")):
        archive = arc_tools.parse_arc(path)
        replacements = {
            entry.index: donor
            for entry in archive.entries
            if "common_018_ID_HQ" in entry.name
        }
        if not replacements:
            continue
        for index in replacements:
            if archive.entries[index].raw_size != len(donor):
                raise ValueError(f"{path}: common_018 size mismatch at entry {index}")
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        for index in replacements:
            if arc_tools.unpack(verified.entries[index]) != donor:
                raise AssertionError(f"verification mismatch: {path} entry {index}")
        report["archives"].append(
            {
                "archive": str(path),
                "entries": sorted(replacements),
                "donor_sha256": arc_tools.sha256(donor),
            }
        )
        report["resources"] += len(replacements)
    report["archive_count"] = len(report["archives"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "COMMON_UI_SYNC_REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "status": "pass",
        "archives": report["archive_count"],
        "resources": report["resources"],
        "donor_sha256": arc_tools.sha256(donor),
    }))


if __name__ == "__main__":
    main()
