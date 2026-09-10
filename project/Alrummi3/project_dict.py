"""The project's own translation memory, used in preference to any model.

The Utage patch carries a hand-built Japanese→English dictionary of ~14,948
entries and a 30-slot character roster whose spellings are read off Samurai
Heroes' own name plates.  Those are authoritative.  A local 7B model is not:
asked to translate 佐竹義重 it answers "Sakata Yoshitaka", where the project
dictionary answers "Yoshishige Satake".

So the order of preference is:

1. the project dictionary, exact key;
2. the dictionary again, through the normalisations below;
3. only then a model, clearly labelled as a guess.

**The glyph-consensus mislabels matter here.** Dictionary keys were produced
by the OCR consensus, which consistently reads び as ぴ, ぶ as ぷ and 使 as
侠.  The project deliberately does not fix that, because the mislabel is
consistent and correcting it would invalidate every key.  A vision model that
reads the character *correctly* will therefore miss the key, so lookups try
the mislabelled spellings too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DICTIONARY_NAME = "utage_dictionary.json"
ROSTER_NAME = "names.py"

# Punctuation the message tables use, per the project's translation notes.
_PUNCTUATION = {
    "＇": "!",
    "？": "?",
    "！": "!",
}

# Known, deliberate glyph-consensus mislabels: correct character -> the
# spelling the dictionary keys actually use.
_CONSENSUS_MISLABELS = {
    "び": "ぴ",
    "ぶ": "ぷ",
    "使": "侠",
    "わ": "ゎ",
    "ぼ": "ぽ",
}

_CONTROL_TAG = re.compile(r"<[A-Z_0-9]+>")


def project_data_dir(app_root: Path) -> Path:
    return Path(app_root) / "project_data"


SUPPLEMENT_NAME = "supplement.json"


def load_dictionary(app_root: Path) -> dict[str, str]:
    """The project's dictionary, plus a clearly separate supplement.

    The supplement carries fixed-vocabulary terms the project dictionary does
    not have - the fortune words on the roulette sheet, for instance. It is a
    separate file and is loaded *underneath* the project's own entries, so a
    project entry always wins and nothing of the user's is overwritten.
    """

    data: dict[str, str] = {}
    supplement = project_data_dir(app_root) / SUPPLEMENT_NAME
    if supplement.is_file():
        try:
            extra = json.loads(supplement.read_text(encoding="utf-8"))
            if isinstance(extra, dict):
                data.update({k: v for k, v in extra.items()
                             if isinstance(v, str) and not k.startswith("_")})
        except (json.JSONDecodeError, OSError):
            pass

    path = project_data_dir(app_root) / DICTIONARY_NAME
    if path.is_file():
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(project, dict):
                data.update(project)
        except (json.JSONDecodeError, OSError):
            pass
    return data


def load_roster(app_root: Path) -> dict[int, list[str]]:
    """Read ROSTER out of the project's names.py without importing it."""

    path = project_data_dir(app_root) / ROSTER_NAME
    if not path.is_file():
        return {}
    roster: dict[int, list[str]] = {}
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"(\d+)\s*:\s*\[([^\]]*)\]", text):
        names = re.findall(r'"([^"]*)"|\'([^\']*)\'', match.group(2))
        flat = [a or b for a, b in names]
        if flat:
            roster[int(match.group(1))] = flat
    return roster


def _variants(japanese: str) -> list[str]:
    """Spellings worth trying against the dictionary, best first.

    **Leading and trailing spaces are significant.**  A key like `" 撤退＇"`
    carries a space where the engine substitutes a name at runtime, so
    stripping before the lookup misses the exact key.  The raw string is
    therefore tried first, and only then the trimmed variants.
    """

    seen: list[str] = []

    def add(value: str, keep_space: bool = False) -> None:
        if not keep_space:
            value = value.strip()
        if value and value not in seen:
            seen.append(value)

    # Exactly as decoded, spaces included.
    add(japanese, keep_space=True)
    base = japanese.strip()
    add(base)
    # Strip readable control tags the MSG viewer adds.
    add(_CONTROL_TAG.sub("", base))
    # Normalise the punctuation the tables use.
    punctuated = base
    for source, target in _PUNCTUATION.items():
        punctuated = punctuated.replace(source, target)
    add(punctuated)
    # The pause marker is written as a bar in the keys.
    add(base.replace("...", "|"))
    add(base.replace("\n", "|"))
    # Try the consensus' deliberate mislabels, since the keys carry them.
    mislabelled = base
    for correct, keyed in _CONSENSUS_MISLABELS.items():
        mislabelled = mislabelled.replace(correct, keyed)
    add(mislabelled)
    # And the reverse, in case the source text is already mislabelled.
    corrected = base
    for correct, keyed in _CONSENSUS_MISLABELS.items():
        corrected = corrected.replace(keyed, correct)
    add(corrected)
    return seen


_CJK = (
    ("぀", "ヿ"),
    ("㐀", "䶿"),
    ("一", "鿿"),
    ("ｦ", "ﾝ"),
)


def has_japanese(text: str) -> bool:
    return any(lo <= ch <= hi for ch in text for lo, hi in _CJK)


def is_already_english(text: str) -> bool:
    """True when a speech carries no Japanese left to translate.

    Plenty of speeches are already English, or are punctuation fragments like
    a lone comma.  Counting those as untranslated makes a survey report work
    that does not exist.
    """

    return bool(text.strip()) and not has_japanese(text)


def lookup(dictionary: dict[str, str], japanese: str) -> tuple[str, str] | None:
    """Return (english, how_it_matched) or None."""

    if not dictionary or not japanese:
        return None
    for index, candidate in enumerate(_variants(japanese)):
        hit = dictionary.get(candidate)
        if hit:
            how = "project dictionary" if index == 0 else "project dictionary (normalised)"
            return hit, how
    # A trailing-punctuation-only difference is common and safe to ignore.
    stripped = japanese.strip().rstrip("。、！？!?｜|・ ")
    if stripped and stripped != japanese:
        hit = dictionary.get(stripped)
        if hit:
            return hit, "project dictionary (trimmed)"
    return None


def search(dictionary: dict[str, str], fragment: str, limit: int = 20) -> list[tuple[str, str]]:
    """Substring search, for when an exact key is not available."""

    if not dictionary or not fragment:
        return []
    fragment = fragment.strip()
    out: list[tuple[str, str]] = []
    for key, value in dictionary.items():
        if fragment in key:
            out.append((key, value))
            if len(out) >= limit:
                break
    return out
