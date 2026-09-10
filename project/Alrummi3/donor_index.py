"""Samurai Heroes donor matching for Alrummi 3.

The local vision and text models are unreliable on Sengoku-era proper nouns —
they will confidently romanize 伊達政宗 as "Iyada Masumune".  The Samurai
Heroes tree is an officially localized release of the same engine, so the
correct English lettering already exists as real textures.  Finding and
reusing one of those beats anything that can be rendered from a font.

This module builds a cached index of candidate donor textures and ranks them
for a given resource.  It never writes to an archive; it only produces images
for the existing review and confirmation flow.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Sequence

from PIL import Image

from alrummi3_core import (
    ArcEntry,
    decode_resource,
    parse_arc,
    type_label,
    unpack_entry,
)

DONOR_INDEX_VERSION = 2
DEFAULT_DONOR_ROOTS = (r"E:\SAMURAI HEROES",)


def donor_index_path(app_root: Path) -> Path:
    return Path(app_root) / "donor_index.json"


def _basename(name: str) -> str:
    return name.replace("/", "\\").split("\\")[-1].lower()


def _loose_key(name: str) -> str:
    """Basename without the language/quality suffixes the trees disagree on."""

    base = _basename(name)
    for suffix in ("_id_hq", "_id_lq", "_id", "_hq", "_lq"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _texture_entries(entries: Sequence[ArcEntry]) -> list[ArcEntry]:
    return [e for e in entries if type_label(e.type_hash, e.name) in ("tex", "texture")]


def build_donor_index(
    roots: Iterable[str | Path] = DEFAULT_DONOR_ROOTS,
    *,
    progress: Callable[[int, int], None] | None = None,
    max_workers: int = 16,
) -> dict:
    """Index every texture entry in the donor trees, keyed by resource name."""

    paths: list[Path] = []
    for root in roots:
        root_path = Path(root)
        if root_path.is_dir():
            paths.extend(
                p for p in root_path.rglob("*")
                if p.is_file() and p.suffix.lower() == ".arc"
            )
    paths.sort(key=lambda p: str(p).lower())
    total = len(paths)

    # Archive id is the position in this list, so a failed parse simply never
    # contributes entries and no id bookkeeping is needed.
    archives = [str(p) for p in paths]
    by_key: dict[str, list[list[int]]] = {}
    by_loose: dict[str, list[list[int]]] = {}
    completed = 0
    skipped = 0

    def index_one(position: int, path: Path):
        archive = parse_arc(path, metadata_only=True)
        return position, _texture_entries(archive.entries)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(index_one, i, p) for i, p in enumerate(paths)]
        for future in as_completed(futures):
            try:
                position, entries = future.result()
            except Exception:
                skipped += 1
                entries = []
                position = -1
            if position >= 0:
                for entry in entries:
                    ref = [position, entry.index]
                    by_key.setdefault(_basename(entry.name), []).append(ref)
                    loose = _loose_key(entry.name)
                    if loose != _basename(entry.name):
                        by_loose.setdefault(loose, []).append(ref)
            completed += 1
            if progress is not None:
                progress(completed, total)

    return {
        "version": DONOR_INDEX_VERSION,
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
        "roots": [str(r) for r in roots],
        "archives": archives,
        "by_key": by_key,
        "by_loose": by_loose,
        "archive_count": total,
        "skipped": skipped,
        "texture_count": sum(len(v) for v in by_key.values()),
    }


def save_donor_index(index: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def load_donor_index(path: Path) -> dict | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(index, dict) or index.get("version") != DONOR_INDEX_VERSION:
        return None
    return index


def find_donor_candidates(
    index: dict,
    resource_name: str,
    *,
    source_archive: str | Path = "",
    limit: int = 24,
    preferred_keys: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """Rank donor textures for a resource, best first.

    Ranking is deliberately explainable: every candidate carries the reason it
    was matched, so a wrong donor is obvious in the list rather than after a
    write.
    """

    archives: list[str] = index.get("archives", [])
    key = _basename(resource_name)
    loose = _loose_key(resource_name)
    source_stem = Path(str(source_archive)).name.lower()

    seen: set[tuple[int, int]] = set()
    candidates: list[dict] = []

    def collect(refs: list[list[int]], tier: int, reason: str) -> None:
        for ref in refs:
            position, entry_index = int(ref[0]), int(ref[1])
            if (position, entry_index) in seen or position >= len(archives):
                continue
            seen.add((position, entry_index))
            archive_path = archives[position]
            lowered = archive_path.lower()
            score = tier * 100
            # An English-branch donor is the whole point, and a donor from the
            # same-named archive is almost always the direct counterpart.
            if "\\eng\\" in lowered or "/eng/" in lowered:
                score -= 30
            if source_stem and Path(archive_path).name.lower() == source_stem:
                score -= 40
            if "\\jpn\\" in lowered or "/jpn/" in lowered:
                score += 20
            candidates.append({
                "archive": archive_path,
                "entry_index": entry_index,
                "tier": tier,
                "reason": reason,
                "score": score,
            })

    # Cross-roster character matches outrank a name match, because the two
    # games number their rosters differently and the name is the unreliable
    # part.  Tier 0 keeps them at the top of the list.
    for preferred_key, reason in preferred_keys or []:
        collect(index.get("by_key", {}).get(preferred_key, []), 0, reason)

    collect(index.get("by_key", {}).get(key, []), 1, "same resource name")
    collect(index.get("by_loose", {}).get(loose, []), 2, "same name ignoring ID/HQ suffix")
    collect(index.get("by_key", {}).get(loose, []), 2, "same name ignoring ID/HQ suffix")

    candidates.sort(key=lambda item: (item["score"], item["archive"], item["entry_index"]))
    return candidates[:limit]


def load_donor_image(archive_path: str | Path, entry_index: int) -> tuple[Image.Image, dict, str]:
    """Decode one donor texture. Returns (image, info, resource name)."""

    archive = parse_arc(Path(archive_path))
    if not 0 <= entry_index < len(archive.entries):
        raise ValueError(f"donor entry {entry_index} is outside {archive_path}")
    entry = archive.entries[entry_index]
    raw = unpack_entry(entry)
    image, info = decode_resource(raw, entry.name)
    return image, info, entry.name


def load_donor_raw(archive_path: str | Path, entry_index: int) -> bytes:
    """Return a donor entry's decompressed resource bytes."""

    archive = parse_arc(Path(archive_path))
    if not 0 <= entry_index < len(archive.entries):
        raise ValueError(f"donor entry {entry_index} is outside {archive_path}")
    return unpack_entry(archive.entries[entry_index])


def describe_candidate(candidate: dict, image: Image.Image | None = None) -> str:
    archive = Path(candidate["archive"])
    size = f"{image.width}x{image.height}  " if image is not None else ""
    return f"{size}{archive.name} #{candidate['entry_index']}  ({candidate['reason']})"


def fit_donor_image(
    donor: Image.Image,
    target_size: tuple[int, int],
    mode: str = "contain",
) -> tuple[Image.Image, dict]:
    """Resize a donor to the target texture's exact dimensions.

    A replacement must match the source dimensions exactly, so every mode
    returns an image of exactly ``target_size``.  The modes differ only in how
    the donor is placed inside it.
    """

    donor = donor.convert("RGBA")
    target_width, target_height = target_size
    if target_width <= 0 or target_height <= 0:
        raise ValueError("target dimensions must be positive")

    if mode == "exact":
        if donor.size != target_size:
            raise ValueError(
                f"donor is {donor.width}x{donor.height}, target is "
                f"{target_width}x{target_height}; choose Fit inside or Stretch"
            )
        result = donor.copy()
        scale = 1.0
        placement = (0, 0)
    elif mode == "stretch":
        result = donor.resize(target_size, Image.Resampling.LANCZOS)
        scale = 0.0
        placement = (0, 0)
    else:  # contain
        scale = min(target_width / donor.width, target_height / donor.height)
        new_size = (max(1, round(donor.width * scale)), max(1, round(donor.height * scale)))
        resized = donor.resize(new_size, Image.Resampling.LANCZOS)
        result = Image.new("RGBA", target_size, (0, 0, 0, 0))
        placement = ((target_width - new_size[0]) // 2, (target_height - new_size[1]) // 2)
        result.alpha_composite(resized, placement)

    return result, {
        "mode": f"donor_{mode}",
        "donor_dimensions": list(donor.size),
        "candidate_dimensions": list(result.size),
        "dimensions_match": result.size == target_size,
        "scale": round(scale, 4),
        "placement": list(placement),
    }
