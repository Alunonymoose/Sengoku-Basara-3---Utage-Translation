"""Plan and apply donor replacements across many archives.

The review gate stays per replacement.  A plan row is a *proposal*, each row
carries the evidence that produced it, and only rows the operator has ticked
are written.  Rows are pre-ticked only when the evidence is as strong as it
gets — a portrait-matched character, a donor of exactly the source
dimensions, and a lossless block copy available — so a weak match is never
silently included.

Nothing here writes over a source archive.  Every output goes to a separate
directory that mirrors the source tree.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from alrummi3_core import (
    decode_xet,
    entry_report,
    parse_arc,
    rebuild_arc,
    sha256,
    swap_xet_payload,
    type_label,
    unpack_entry,
    verify_single_replacement,
)
from character_map import translate_resource
from donor_index import find_donor_candidates, load_donor_raw


def _basename(name: str) -> str:
    return name.replace("/", "\\").split("\\")[-1]


def plan_batch(
    archive_paths: Sequence[str | Path],
    donor_index: dict,
    character_map: dict | None,
    *,
    families: Iterable[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], list[str]]:
    """Propose one donor replacement per texture entry that has a good match.

    ``families`` optionally restricts to resource prefixes such as
    ``cp_name_pl``; without it every texture entry is considered.
    """

    wanted = tuple(f.lower() for f in families) if families else None
    rows: list[dict] = []
    errors: list[str] = []
    total = len(archive_paths)

    for position, archive_path in enumerate(archive_paths, start=1):
        try:
            archive = parse_arc(Path(archive_path))
        except Exception as exc:
            errors.append(f"{archive_path}: {exc}")
            if progress:
                progress(position, total)
            continue

        for entry in archive.entries:
            if type_label(entry.type_hash, entry.name) not in ("tex", "texture"):
                continue
            base = _basename(entry.name).lower()
            if wanted and not base.startswith(wanted):
                continue
            try:
                raw = unpack_entry(entry)
                if raw[:4] != b"\0XET":
                    continue
                source_image, source_info = decode_xet(raw)
            except Exception:
                continue
            if source_info.fourcc not in ("DXT1", "DXT5"):
                # Anything the block encoder cannot produce is not proposed.
                continue

            preferred: list[tuple[str, str]] = []
            matched = translate_resource(character_map, entry.name)
            if matched is not None:
                donor_key, info = matched
                preferred.append((
                    donor_key,
                    f"same character, matched on {info['matched_on']} (distance {info['distance']})",
                ))

            candidates = find_donor_candidates(
                donor_index,
                entry.name,
                source_archive=str(archive.path),
                limit=6,
                preferred_keys=preferred,
            )
            chosen = None
            for candidate in candidates:
                try:
                    donor_raw = load_donor_raw(candidate["archive"], candidate["entry_index"])
                    if donor_raw[:4] != b"\0XET":
                        continue
                    donor_image, donor_info = decode_xet(donor_raw)
                except Exception:
                    continue
                if donor_image.size != source_image.size:
                    continue
                lossless = False
                identical = False
                try:
                    replacement = swap_xet_payload(raw, donor_raw)
                    lossless = True
                    # The eng branch may already carry this exact donor from
                    # earlier transplant work.  That is a result worth showing,
                    # not a replacement worth writing again.
                    identical = replacement == raw
                except Exception:
                    lossless = False
                chosen = {
                    "archive": str(archive.path),
                    "entry_index": entry.index,
                    "resource": entry.name,
                    "size": list(source_image.size),
                    "donor_archive": candidate["archive"],
                    "donor_entry_index": candidate["entry_index"],
                    "tier": candidate["tier"],
                    "reason": candidate["reason"],
                    "lossless": lossless,
                    "already_applied": identical,
                    # Only the strongest evidence is pre-ticked: a portrait
                    # match, exact dimensions, a lossless copy available, and
                    # something actually left to change.
                    "use": candidate["tier"] == 0 and lossless and not identical,
                }
                break
            if chosen is not None:
                rows.append(chosen)

        if progress:
            progress(position, total)

    return rows, errors


def apply_batch(
    rows: Sequence[dict],
    output_root: str | Path,
    source_root: str | Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Write every ticked row, one new archive per source archive.

    Replacements are grouped by archive so an archive with several matched
    textures is rebuilt once, and every write is verified before it counts.
    """

    output_root = Path(output_root)
    source_root = Path(source_root)
    selected = [row for row in rows if row.get("use")]
    grouped: dict[str, list[dict]] = {}
    for row in selected:
        grouped.setdefault(row["archive"], []).append(row)

    written: list[dict] = []
    failures: list[str] = []
    already_identical = 0
    total = len(grouped)

    for position, (archive_path, group) in enumerate(sorted(grouped.items()), start=1):
        try:
            archive = parse_arc(Path(archive_path))
            replacements: dict[int, bytes] = {}
            details: list[dict] = []
            skipped_identical = 0
            for row in group:
                entry = archive.entries[row["entry_index"]]
                raw = unpack_entry(entry)
                donor_raw = load_donor_raw(row["donor_archive"], row["donor_entry_index"])
                if not row.get("lossless"):
                    raise ValueError("only lossless donor copies are written in batch mode")
                replacement = swap_xet_payload(raw, donor_raw)
                method = "lossless_block_copy"
                if replacement == raw:
                    # Already carries this donor; writing it would be a no-op.
                    skipped_identical += 1
                    continue
                replacements[entry.index] = replacement
                details.append({
                    "entry_index": entry.index,
                    "resource": entry.name,
                    "donor_archive": row["donor_archive"],
                    "donor_entry_index": row["donor_entry_index"],
                    "reason": row["reason"],
                    "tier": row["tier"],
                    "method": method,
                    "before": entry_report(entry, raw),
                })

            if not replacements:
                already_identical += skipped_identical
                if progress:
                    progress(position, total)
                continue

            rebuilt = rebuild_arc(archive, replacements)

            try:
                relative = Path(archive_path).relative_to(source_root)
            except ValueError:
                relative = Path(Path(archive_path).name)
            destination = output_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.resolve() == Path(archive_path).resolve():
                raise ValueError("refusing to write over the source archive")
            destination.write_bytes(rebuilt)

            after = parse_arc(destination)
            changed = [
                index for index in range(len(archive.entries))
                if archive.entries[index].compressed != after.entries[index].compressed
            ]
            if sorted(changed) != sorted(replacements):
                raise AssertionError(
                    f"expected entries {sorted(replacements)} to change, got {sorted(changed)}"
                )

            audit = {
                "tool": "Alrummi 3 batch",
                "written": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": str(archive_path),
                "source_sha256": archive.data_sha256,
                "output": str(destination),
                "output_sha256": sha256(rebuilt),
                "entries_changed": sorted(replacements),
                "entry_count": len(archive.entries),
                "replacements": details,
            }
            audit_path = destination.with_suffix(destination.suffix + ".audit.json")
            audit_path.write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
            written.append({"output": str(destination), "entries": sorted(replacements)})
        except Exception as exc:
            failures.append(f"{archive_path}: {exc}")
        if progress:
            progress(position, total)

    return {
        "archives_written": len(written),
        "already_identical": already_identical,
        "replacements_written": sum(len(w["entries"]) for w in written),
        "written": written,
        "failures": failures,
        "output_root": str(output_root),
    }
