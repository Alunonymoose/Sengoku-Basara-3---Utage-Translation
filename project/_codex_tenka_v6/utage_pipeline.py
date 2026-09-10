from __future__ import annotations

"""Unified read-only inventory and validation CLI for Utage ARC projects."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arc_tools  # noqa: E402


MAGIC_TYPES = {
    b"\x00XET": "XET",
    b"\x00TNF": "TNF",
    b"\x00GSM": "GSM",
    b"\x00FIM": "FIM",
    b"\x00CSA": "CSA",
    b"LSP\x00": "LSP",
}


def classify(raw: bytes) -> str:
    for magic, kind in MAGIC_TYPES.items():
        if raw.startswith(magic):
            return kind
    if raw.startswith(b"\x00CRA") or raw.startswith(b"ARC\x00"):
        return "ARC"
    return "unknown"


def inventory(root: Path) -> dict:
    archives = []
    formats = Counter()
    errors = []
    for path in sorted(root.rglob("*.arc")):
        try:
            archive = arc_tools.parse_arc(path)
            entries = []
            for entry in archive.entries:
                raw = arc_tools.unpack(entry)
                if len(raw) != entry.raw_size:
                    raise ValueError(
                        f"entry {entry.index} raw size mismatch: "
                        f"declared {entry.raw_size}, decoded {len(raw)}"
                    )
                kind = classify(raw)
                formats[kind] += 1
                entries.append(
                    {
                        "index": entry.index,
                        "name": entry.name,
                        "type_hash": f"0x{entry.type_hash:08X}",
                        "raw_size": len(raw),
                        "declared_raw_size": entry.raw_size,
                        "format": kind,
                        "raw_sha256": arc_tools.sha256(raw),
                    }
                )
            archives.append(
                {
                    "path": str(path.relative_to(root)),
                    "size": len(archive.data),
                    "sha256": arc_tools.sha256(archive.data),
                    "version": archive.version,
                    "entry_count": len(archive.entries),
                    "entries": entries,
                }
            )
        except Exception as exc:
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})
    return {
        "root": str(root),
        "archive_count": len(archives),
        "resource_count": sum(item["entry_count"] for item in archives),
        "format_counts": dict(sorted(formats.items())),
        "errors": errors,
        "archives": archives,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "UTAGE_PIPELINE_MANIFEST.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any archive entry has a decoded-size mismatch or unknown format",
    )
    args = parser.parse_args()
    result = inventory(args.root)
    if args.strict:
        unknown = sum(
            1
            for archive in result["archives"]
            for entry in archive["entries"]
            if entry["format"] == "unknown"
        )
        if unknown:
            result["errors"].append(
                {"path": str(args.root), "error": f"{unknown} unknown resource formats"}
            )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "pass" if not result["errors"] else "error",
                "archives": result["archive_count"],
                "resources": result["resource_count"],
                "formats": result["format_counts"],
                "errors": len(result["errors"]),
                "manifest": str(args.output),
            }
        )
    )
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
