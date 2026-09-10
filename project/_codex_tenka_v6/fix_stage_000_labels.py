from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arc_tools  # noqa: E402

ROOT = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng")
DONOR = ROOT / "tenka" / "tenka_stage_m000.arc"
TARGETS = (
    ROOT / "common" / "mission" / "m000.arc",
    ROOT / "result_id.arc",
    ROOT / "tenka" / "tenka_finish_id.arc",
)
RESOURCE_NAME = r"id\texture\jpn\stage\stage_000_ID_HQ"


def main() -> None:
    donor = arc_tools.parse_arc(DONOR)
    donor_entries = [entry for entry in donor.entries if entry.name == RESOURCE_NAME]
    if len(donor_entries) != 1:
        raise ValueError(f"expected one donor resource, found {len(donor_entries)}")
    donor_raw = arc_tools.unpack(donor_entries[0])
    donor_hash = arc_tools.sha256(donor_raw)
    report = {"donor": str(DONOR), "donor_raw_sha256": donor_hash, "updated": []}

    for path in TARGETS:
        archive = arc_tools.parse_arc(path)
        matches = [entry for entry in archive.entries if entry.name == RESOURCE_NAME]
        if len(matches) != 1:
            raise ValueError(f"{path}: expected one target resource, found {len(matches)}")
        target = matches[0]
        old_hash = arc_tools.sha256(arc_tools.unpack(target))
        if old_hash == donor_hash:
            continue
        rebuilt = arc_tools.rebuild(archive, {target.index: donor_raw})
        temporary = path.with_suffix(path.suffix + ".stage000.tmp")
        temporary.write_bytes(rebuilt)
        verification = arc_tools.parse_arc(temporary)
        verified = arc_tools.sha256(arc_tools.unpack(verification.entries[target.index]))
        if verified != donor_hash:
            temporary.unlink()
            raise ValueError(f"{path}: rebuilt resource hash verification failed")
        temporary.replace(path)
        report["updated"].append(
            {
                "path": str(path),
                "entry": target.index,
                "old_raw_sha256": old_hash,
                "new_raw_sha256": donor_hash,
            }
        )

    output = HERE / "STAGE_000_LABEL_FIX_REPORT.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "updated": len(report["updated"]), "report": str(output)}))


if __name__ == "__main__":
    main()
