"""Survey and build English dialogue archives in bulk.

The project has 1,410 dialogue archives and the hand-built dictionary already
covers about 99% of their speeches, so the remaining work is not translation -
it is running the build safely over all of them and looking at what falls out.

Two passes, deliberately separate:

* **Survey** decodes every archive and reports how much the dictionary covers,
  what still needs wording, and what would fail validation.  It writes
  nothing and keeps only counts, so memory stays flat over a thousand
  archives.
* **Build** re-decodes each archive it is told to, assembles it, checks the
  project's five invariants, and writes it **only if all five pass**.  An
  archive that fails is reported and skipped, never written.

Output always goes to a separate tree.  No source archive is touched.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Sequence

import msg_edit
from alrummi3_core import sha256
from project_dict import is_already_english, lookup as dict_lookup


def survey(
    paths: Sequence[Path],
    glyph_maps: dict,
    dictionary: dict,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Report dictionary coverage per archive without writing anything."""

    rows: list[dict] = []
    total = len(paths)
    for position, path in enumerate(paths, start=1):
        entry = {
            "path": str(path),
            "name": path.name,
            "speeches": 0,
            "japanese": 0,
            "filled": 0,
            "already_english": 0,
            "missing": 0,
            "problems": 0,
            "has_glyph_map": path.name in glyph_maps,
            "error": "",
        }
        try:
            decoded = msg_edit.decode_archive(path, glyph_maps.get(path.name, {}))
        except Exception as exc:
            entry["error"] = str(exc)
            rows.append(entry)
            if progress:
                progress(position, total)
            continue

        for row in decoded:
            entry["speeches"] += 1
            japanese = row["japanese"]
            if not japanese.strip():
                continue
            entry["japanese"] += 1
            hit = dict_lookup(dictionary, japanese)
            if hit:
                entry["filled"] += 1
                row["english"] = hit[0]
                if msg_edit.validate_row(row):
                    entry["problems"] += 1
            elif is_already_english(japanese):
                # Nothing left to translate here; counting it as outstanding
                # would report work that does not exist.
                entry["already_english"] += 1
            else:
                entry["missing"] += 1
        # Ready means every Japanese speech has wording and none of it breaks
        # the plate's line rules.
        entry["ready"] = (
            not entry["error"]
            and entry["has_glyph_map"]
            and entry["missing"] == 0
            and entry["problems"] == 0
        )
        entry["use"] = entry["ready"]
        rows.append(entry)
        if progress:
            progress(position, total)
    return rows


def build_batch(
    rows: Sequence[dict],
    rom_root: Path,
    output_root: Path,
    glyph_maps: dict,
    dictionary: dict,
    *,
    overrides: dict[str, dict] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Build every ticked archive, writing only the ones that verify.

    ``overrides`` maps an archive name to {(gsm, record, speech): english} for
    wording signed off by hand, which takes precedence over the dictionary.
    """

    rom_root = Path(rom_root)
    output_root = Path(output_root)
    selected = [r for r in rows if r.get("use")]
    written: list[dict] = []
    failed: list[dict] = []
    total = len(selected)

    for position, row in enumerate(selected, start=1):
        path = Path(row["path"])
        try:
            donor = msg_edit.find_latin_donor(path, rom_root)
            if donor is None:
                raise ValueError("no Samurai Heroes donor available for the Latin font")

            decoded = msg_edit.decode_archive(path, glyph_maps.get(path.name, {}))
            manual = (overrides or {}).get(path.name, {})
            filled = 0
            for item in decoded:
                key = (item["gsm"], item["record"], item["speech"])
                if key in manual:
                    item["english"] = manual[key]
                    filled += 1
                    continue
                if item["japanese"].strip():
                    hit = dict_lookup(dictionary, item["japanese"])
                    if hit:
                        item["english"] = hit[0]
                        filled += 1

            built, stats = msg_edit.build_english_archive(path, donor, decoded)
            report = msg_edit.verify_english_build(path, built)
            if report["status"] != "pass":
                failed.append({
                    "name": path.name,
                    "reason": "invariants failed: " + ", ".join(report["failed"]),
                })
                if progress:
                    progress(position, total)
                continue

            try:
                relative = path.relative_to(rom_root)
            except ValueError:
                relative = Path(path.name)
            destination = output_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.resolve() == path.resolve():
                raise ValueError("refusing to write over the source archive")
            destination.write_bytes(built)
            destination.with_suffix(destination.suffix + ".audit.json").write_text(
                json.dumps({
                    "tool": "Alrummi 3 dialogue batch",
                    "written": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": str(path),
                    "donor": str(donor),
                    "output": str(destination),
                    "output_sha256": sha256(built),
                    "stats": stats,
                    "invariants": report["checks"],
                    "hand_signed": len(manual),
                }, indent=1, ensure_ascii=False),
                encoding="utf-8",
            )
            written.append({
                "name": path.name,
                "output": str(destination),
                "translated": stats["translated"],
                "transliterated": stats["transliterated"],
                "passthrough_english": stats.get("passthrough_english", 0),
                "japanese_lost": stats.get("japanese_lost", 0),
            })
        except Exception as exc:
            failed.append({"name": path.name, "reason": str(exc)})
        if progress:
            progress(position, total)

    return {
        "written": written,
        "failed": failed,
        "archives_written": len(written),
        "archives_failed": len(failed),
        "output_root": str(output_root),
        "translated": sum(w["translated"] for w in written),
        "transliterated": sum(w["transliterated"] for w in written),
        "passthrough_english": sum(w.get("passthrough_english", 0) for w in written),
        "japanese_lost": sum(w.get("japanese_lost", 0) for w in written),
    }


def summarise(rows: Sequence[dict]) -> dict:
    return {
        "archives": len(rows),
        "ready": sum(1 for r in rows if r.get("ready")),
        "speeches": sum(r["speeches"] for r in rows),
        "japanese": sum(r["japanese"] for r in rows),
        "filled": sum(r["filled"] for r in rows),
        "already_english": sum(r.get("already_english", 0) for r in rows),
        "missing": sum(r["missing"] for r in rows),
        "problems": sum(r["problems"] for r in rows),
        "errors": sum(1 for r in rows if r.get("error")),
        "no_glyph_map": sum(1 for r in rows if not r.get("has_glyph_map")),
    }
