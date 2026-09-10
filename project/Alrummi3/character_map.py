"""Cross-roster character matching between Utage and Samurai Heroes.

The two games number their character rosters differently.  Utage's
``cp_name_pl_105`` (佐竹義重) is Samurai Heroes' ``cp_name_pl_028``
("Yoshishige Satake"), so matching donor textures by resource name silently
misses every character whose id was renumbered — which is most of them.

The portrait artwork, however, is byte-identical between the two releases.
Matching a character's face texture therefore identifies the same person
across both games regardless of language or index, and the correct English
nameplate is then simply the same index on the Samurai Heroes side.

Measured on real data: every tested character matched at signature distance
0.00 with a large margin over the runner-up.  The family crest alone is not
enough — Masamune Date and Kojuro Katakura share the Date clan kamon — so the
face is the identifier and the kamon is only a fallback.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from donor_index import load_donor_image

CHARACTER_MAP_VERSION = 1

DEFAULT_LOCAL_ROOTS = (r"E:\Utage Patching New\PS3_GAME",)


def local_index_path(app_root: Path) -> Path:
    return Path(app_root) / "local_index.json"

# Per-character texture families, best identifier first.  The face is unique
# to a person; the crest is only unique to a clan.
IDENTITY_PREFIXES = ("cp_face_msg", "cp_face_army", "kamon")

# e.g. "cp_name_pl_105_id_hq" -> ("cp_name_pl", "105", "_id_hq")
_RESOURCE_RE = re.compile(r"^(?P<prefix>.+?)_(?P<index>\d{3})(?P<suffix>_.*)?$")

SIGNATURE_SIZE = (32, 32)
# A confident match is near zero and far from the runner-up.  These bounds
# come from the measured data, where true matches were 0.00 and the nearest
# wrong answer was 40 or more.
MAX_MATCH_DISTANCE = 12.0
MIN_MATCH_MARGIN = 15.0


def split_resource(name: str) -> tuple[str, str, str] | None:
    """Split a resource basename into (family prefix, index, suffix)."""

    base = name.replace("/", "\\").split("\\")[-1].lower()
    match = _RESOURCE_RE.match(base)
    if match is None:
        return None
    return match["prefix"], match["index"], match["suffix"] or ""


def signature(image: Image.Image) -> tuple[list[int], list[int]]:
    """A small luma+alpha fingerprint, tolerant of block-compression noise."""

    small = image.convert("RGBA").resize(SIGNATURE_SIZE, Image.Resampling.LANCZOS)
    try:
        luma = list(small.convert("L").get_flattened_data())
        alpha = list(small.getchannel("A").get_flattened_data())
    except AttributeError:  # older Pillow
        luma = list(small.convert("L").getdata())
        alpha = list(small.getchannel("A").getdata())
    return luma, alpha


def signature_distance(a: tuple[list[int], list[int]], b: tuple[list[int], list[int]]) -> float:
    luma_a, alpha_a = a
    luma_b, alpha_b = b
    count = len(luma_a)
    if count == 0 or count != len(luma_b):
        return float("inf")
    luma = sum(abs(x - y) for x, y in zip(luma_a, luma_b)) / count
    alpha = sum(abs(x - y) for x, y in zip(alpha_a, alpha_b)) / count
    return luma + alpha


def _representative_refs(index: dict, prefix: str) -> dict[str, tuple[str, int]]:
    """One entry per character index for a texture family, English preferred."""

    chosen: dict[str, tuple[str, int]] = {}
    archives = index.get("archives", [])
    for key, refs in index.get("by_key", {}).items():
        parsed = split_resource(key)
        if parsed is None or parsed[0] != prefix:
            continue
        character = parsed[1]
        if character in chosen:
            continue
        preferred = None
        for position, entry_index in refs:
            if position >= len(archives):
                continue
            lowered = archives[position].lower()
            if "\\eng\\" in lowered or "/eng/" in lowered:
                preferred = (archives[position], entry_index)
                break
        if preferred is None:
            position, entry_index = refs[0]
            if position < len(archives):
                preferred = (archives[position], entry_index)
        if preferred is not None:
            chosen[character] = preferred
    return chosen


def _signatures(refs: dict[str, tuple[str, int]], progress=None, label="") -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    total = len(refs)
    for done, (character, (archive, entry_index)) in enumerate(sorted(refs.items()), start=1):
        try:
            image, _info, _name = load_donor_image(archive, entry_index)
            out[character] = signature(image)
        except Exception:
            pass
        if progress is not None:
            progress(done, total, label)
    return out


def build_character_map(
    local_index: dict,
    donor_index: dict,
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Map local (Utage) character indices onto donor (SH) character indices."""

    mapping: dict[str, dict] = {}
    used_prefix: dict[str, str] = {}

    for prefix in IDENTITY_PREFIXES:
        local_refs = _representative_refs(local_index, prefix)
        donor_refs = _representative_refs(donor_index, prefix)
        if not local_refs or not donor_refs:
            continue
        donor_sigs = _signatures(donor_refs, progress, f"{prefix} (donor)")
        local_sigs = _signatures(local_refs, progress, f"{prefix} (local)")
        if not donor_sigs:
            continue
        for character, sig in local_sigs.items():
            if character in mapping:
                continue  # an earlier, stronger family already decided this one
            ranked = sorted(
                (signature_distance(sig, other), donor_character)
                for donor_character, other in donor_sigs.items()
            )
            if not ranked:
                continue
            best_distance, best_character = ranked[0]
            margin = (ranked[1][0] - best_distance) if len(ranked) > 1 else float("inf")
            if best_distance <= MAX_MATCH_DISTANCE and margin >= MIN_MATCH_MARGIN:
                mapping[character] = {
                    "donor_character": best_character,
                    "distance": round(best_distance, 3),
                    "margin": round(margin, 3) if margin != float("inf") else None,
                    "matched_on": prefix,
                }
                used_prefix[character] = prefix

    return {
        "version": CHARACTER_MAP_VERSION,
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
        "matched": len(mapping),
        "map": mapping,
    }


def character_map_path(app_root: Path) -> Path:
    return Path(app_root) / "character_map.json"


def save_character_map(data: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def load_character_map(path: Path) -> dict | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("version") != CHARACTER_MAP_VERSION:
        return None
    return data


def translate_resource(character_map: dict | None, resource_name: str) -> tuple[str, dict] | None:
    """Rewrite a local resource name onto its donor-side counterpart."""

    if not character_map:
        return None
    parsed = split_resource(resource_name)
    if parsed is None:
        return None
    prefix, character, suffix = parsed
    entry = character_map.get("map", {}).get(character)
    if entry is None:
        return None
    return f"{prefix}_{entry['donor_character']}{suffix}", entry
