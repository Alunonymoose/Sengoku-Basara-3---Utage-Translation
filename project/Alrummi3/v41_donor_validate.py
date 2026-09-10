"""Fail-closed donor validation for Alrummi 3 V4.1.

A donor is not useful merely because its resource name, size, or XET layout
matches.  This module validates a candidate against the currently selected
Utage texture before V4 is allowed to stop on the donor route.

The policy deliberately prefers a false negative (fall through to rebuild) to
a false positive (show the same Japanese texture and call it an English fix).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

import numpy as np
from PIL import Image

import v4_mttex_codec as codec


# Hiragana, katakana, CJK and halfwidth katakana.  CJK also includes Chinese,
# but for this Japanese PS3 game it is the correct conservative signal: a
# supposed English donor containing only these glyphs should not be trusted.
_JP_RANGES = (
    (0x3040, 0x309F),
    (0x30A0, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFF66, 0xFF9F),
)


def _is_jp_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _JP_RANGES)


def japanese_chars(text: str) -> str:
    return "".join(ch for ch in str(text) if _is_jp_char(ch))


def latin_chars(text: str) -> str:
    return "".join(ch for ch in str(text) if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).strip().lower()


def provider_from_path(path: str | Path) -> str:
    """Classify archive provenance without trusting the resource's jpn segment.

    Basara resources can retain ``id\\texture\\jpn`` internally even when the
    archive is an official English-provider ARC, so only the *archive path* is
    used for this decision.
    """
    text = str(path).replace("/", "\\").lower()
    parts = [p for p in text.split("\\") if p]
    if "jpn" in parts:
        return "jpn"
    if "eng" in parts:
        return "eng"
    if "samurai heroes" in text or "samurai_heroes" in text:
        return "samurai_heroes_unknown"
    return "unknown"


def read_ocr_text(engine, image: Image.Image) -> str:
    """Read a sheet only for validation; OCR never authors English here."""
    if engine is None:
        return ""
    rows = []
    try:
        rows = engine.read_regions(image, scale=3)
    except Exception:
        try:
            rows = engine.read_regions(image, scale=2)
        except Exception:
            return ""
    return " ".join(str(getattr(row, "text", "")).strip() for row in rows if str(getattr(row, "text", "")).strip())


def image_metrics(source: Image.Image, donor: Image.Image) -> dict:
    if source.size != donor.size:
        return {
            "same_size": False,
            "pixel_equal": False,
            "changed_fraction": 1.0,
            "mean_abs_error": 255.0,
            "alpha_occupancy_xor": 1.0,
        }
    a = np.asarray(source.convert("RGBA"), dtype=np.int16)
    b = np.asarray(donor.convert("RGBA"), dtype=np.int16)
    delta = np.abs(a - b)
    changed = np.any(delta != 0, axis=2)
    alpha_a = a[..., 3] > 8
    alpha_b = b[..., 3] > 8
    return {
        "same_size": True,
        "pixel_equal": bool(np.array_equal(a, b)),
        "changed_fraction": float(changed.mean()),
        "mean_abs_error": float(delta.mean()),
        "alpha_occupancy_xor": float(np.logical_xor(alpha_a, alpha_b).mean()),
    }


def _xet_layout(raw: bytes) -> dict | None:
    if not raw.startswith(b"\0XET"):
        return None
    try:
        info = codec.parse_xet(raw)
    except Exception:
        return None
    return {
        "width": info.width,
        "height": info.height,
        "format_code": info.format_code,
        "fourcc": info.fourcc,
        "mip_count": info.mip_count,
        "shader": info.shader,
    }


@dataclass
class DonorVerdict:
    accepted: bool
    score: int
    reasons: list[str]
    warnings: list[str]
    provider: str
    source_ocr: str
    donor_ocr: str
    source_japanese: str
    donor_japanese: str
    donor_latin: str
    changed_fraction: float
    mean_abs_error: float
    alpha_occupancy_xor: float
    exact_xet_layout: bool

    def as_dict(self) -> dict:
        return asdict(self)


def validate_donor(
    source_image: Image.Image,
    source_raw: bytes,
    donor_image: Image.Image,
    donor_raw: bytes,
    donor_archive: str | Path,
    *,
    ocr_engine=None,
    source_ocr: str | None = None,
) -> DonorVerdict:
    """Return a multi-signal verdict for one proposed official donor."""
    reasons: list[str] = []
    warnings: list[str] = []
    provider = provider_from_path(donor_archive)
    metrics = image_metrics(source_image, donor_image)

    if not metrics["same_size"]:
        reasons.append("dimensions differ from the selected texture")

    if source_raw == donor_raw:
        reasons.append("decompressed donor resource is byte-identical to the source")

    if metrics["pixel_equal"]:
        reasons.append("decoded donor image is pixel-identical to the source")
    elif metrics["changed_fraction"] < 0.0005 and metrics["mean_abs_error"] < 0.20:
        reasons.append("decoded donor is effectively identical to the source")

    # A same-family English donor should retain the same sprite geometry.  This
    # still leaves plenty of room for different glyph alpha while rejecting a
    # completely different same-size atlas.
    if metrics["alpha_occupancy_xor"] > 0.22:
        reasons.append(
            f"sprite/alpha geometry differs too much ({metrics['alpha_occupancy_xor']:.1%})"
        )

    if provider == "jpn":
        reasons.append("candidate archive is explicitly from a /jpn/ provider")
    elif provider == "unknown":
        warnings.append("archive language provider is unknown")

    source_layout = _xet_layout(source_raw)
    donor_layout = _xet_layout(donor_raw)
    exact_layout = bool(source_layout is not None and donor_layout is not None and source_layout == donor_layout)
    if source_layout is not None and donor_layout is not None:
        if (source_layout["width"], source_layout["height"]) != (donor_layout["width"], donor_layout["height"]):
            reasons.append("XET dimensions differ")
        if source_layout["shader"] != donor_layout["shader"]:
            warnings.append("XET display shader differs; donor would require re-encoding")
        if source_layout["format_code"] != donor_layout["format_code"]:
            warnings.append("XET storage format differs; donor would require re-encoding")
        if source_layout["mip_count"] != donor_layout["mip_count"]:
            warnings.append("XET mip count differs; donor cannot be copied losslessly")

    if source_ocr is None:
        source_ocr = read_ocr_text(ocr_engine, source_image)
    donor_ocr = read_ocr_text(ocr_engine, donor_image)
    src_norm = normalized_text(source_ocr)
    donor_norm = normalized_text(donor_ocr)
    src_jp = japanese_chars(source_ocr)
    donor_jp = japanese_chars(donor_ocr)
    donor_latin = latin_chars(donor_ocr)

    if src_norm and donor_norm and src_norm == donor_norm:
        reasons.append(f"OCR reads the same text in source and donor: {donor_ocr!r}")

    if donor_jp and not donor_latin:
        reasons.append(f"donor OCR still reads Japanese/CJK text: {donor_ocr!r}")
    elif src_jp and donor_jp:
        shared = sum(1 for ch in set(src_jp) if ch in donor_jp)
        denom = max(1, len(set(src_jp)))
        if shared / denom >= 0.50:
            reasons.append("donor retains most of the Japanese glyphs detected in the source")

    # If the source is demonstrably Japanese, fail closed unless we can see an
    # English signal in the donor.  A false negative simply sends Fix Texture
    # on to the rebuild path; a false positive leaves the game untranslated.
    if src_jp and not donor_latin and not donor_jp:
        reasons.append("source OCR is Japanese but donor OCR gives no evidence of English lettering")

    score = 0
    if provider == "eng":
        score += 3
    elif provider == "samurai_heroes_unknown":
        score += 1
    if donor_latin:
        score += 4
    if src_jp and donor_latin and not donor_jp:
        score += 4
    if exact_layout:
        score += 2
    if metrics["changed_fraction"] >= 0.0005:
        score += 1
    if metrics["alpha_occupancy_xor"] <= 0.06:
        score += 1

    # No source OCR is common on tiny or highly stylised labels.  In that case
    # an explicit /eng/ provider + visible change + compatible geometry is
    # enough to try the donor.  When the source *is* read as Japanese, demand
    # stronger evidence that English replaced it.
    minimum = 8 if src_jp else 6
    if score < minimum:
        reasons.append(f"only {score} donor-confidence points; {minimum} required")

    return DonorVerdict(
        accepted=not reasons,
        score=score,
        reasons=reasons,
        warnings=warnings,
        provider=provider,
        source_ocr=str(source_ocr or ""),
        donor_ocr=str(donor_ocr or ""),
        source_japanese=src_jp,
        donor_japanese=donor_jp,
        donor_latin=donor_latin,
        changed_fraction=metrics["changed_fraction"],
        mean_abs_error=metrics["mean_abs_error"],
        alpha_occupancy_xor=metrics["alpha_occupancy_xor"],
        exact_xet_layout=exact_layout,
    )


def candidate_quality(source: Image.Image, candidate: Image.Image, *, ocr_engine=None, source_ocr: str = "") -> dict:
    """Cheap no-op/Japanese-remains gate for generated candidates."""
    metrics = image_metrics(source, candidate)
    candidate_ocr = read_ocr_text(ocr_engine, candidate)
    src_jp = japanese_chars(source_ocr)
    cand_jp = japanese_chars(candidate_ocr)
    reasons: list[str] = []
    if metrics["pixel_equal"] or (
        metrics["changed_fraction"] < 0.0005 and metrics["mean_abs_error"] < 0.20
    ):
        reasons.append("candidate is visually unchanged")
    if src_jp and cand_jp and normalized_text(source_ocr) == normalized_text(candidate_ocr):
        reasons.append("candidate OCR still reads exactly the same Japanese text")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "source_ocr": source_ocr,
        "candidate_ocr": candidate_ocr,
        "changed_fraction": metrics["changed_fraction"],
        "mean_abs_error": metrics["mean_abs_error"],
    }
