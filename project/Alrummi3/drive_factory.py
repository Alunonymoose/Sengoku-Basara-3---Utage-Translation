"""Drive-backed ChatGPT handoff for Alrummi 3.

This module deliberately does *not* call an OpenAI API and never writes an ARC.
It turns a locally synced Google Drive folder into a safe job queue:

    Alrummi3_AI_Factory/
        INBOX/JOB_.../       source/reference/prompt/manifest
        OUTBOX/JOB_.../      replacement.png + optional result.json
        DONE/JOB_.../        archived accepted jobs
        REJECTED/JOB_.../    archived rejected outputs

Google Drive for desktop handles transport.  ChatGPT (or a human) performs the
image edit and writes ``replacement.png`` to the matching OUTBOX job folder.
Alrummi can poll for that file, validate it, then load it as a *candidate*.
Nothing in this module installs or patches game data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import string
from typing import Any, Iterable, Sequence

from PIL import Image, ImageChops, ImageStat


SCHEMA_VERSION = 1
DEFAULT_FACTORY_NAME = "Alrummi3_AI_Factory"
RESULT_NAME = "replacement.png"
RESULT_META_NAME = "result.json"
READY_NAME = ".ready"


class FactoryError(RuntimeError):
    """A factory job could not be created or consumed safely."""


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def from_any(cls, value: Any) -> "Box":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            if {"left", "top", "right", "bottom"} <= set(value):
                return cls(*(int(value[k]) for k in ("left", "top", "right", "bottom")))
            if {"x", "y", "width", "height"} <= set(value):
                x = int(value["x"])
                y = int(value["y"])
                return cls(x, y, x + int(value["width"]), y + int(value["height"]))
        if isinstance(value, Sequence) and len(value) == 4:
            a, b, c, d = (int(v) for v in value)
            return cls(a, b, c, d)
        raise ValueError(f"Cannot convert to Box: {value!r}")

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def clamp(self, width: int, height: int) -> "Box":
        return Box(
            max(0, min(width, self.left)),
            max(0, min(height, self.top)),
            max(0, min(width, self.right)),
            max(0, min(height, self.bottom)),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class FactoryConfig:
    root: Path
    max_outside_change_ratio: float = 0.002
    pixel_difference_threshold: int = 12
    require_same_alpha_size: bool = True

    @property
    def inbox(self) -> Path:
        return self.root / "INBOX"

    @property
    def outbox(self) -> Path:
        return self.root / "OUTBOX"

    @property
    def done(self) -> Path:
        return self.root / "DONE"

    @property
    def rejected(self) -> Path:
        return self.root / "REJECTED"

    def ensure(self) -> None:
        for path in (self.root, self.inbox, self.outbox, self.done, self.rejected):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class FactoryJob:
    job_id: str
    inbox_dir: Path
    outbox_dir: Path
    manifest_path: Path
    source_path: Path
    width: int
    height: int
    editable_regions: tuple[Box, ...] = field(default_factory=tuple)

    @property
    def result_path(self) -> Path:
        return self.outbox_dir / RESULT_NAME

    @property
    def result_meta_path(self) -> Path:
        return self.outbox_dir / RESULT_META_NAME


@dataclass
class ValidationResult:
    ok: bool
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def require_ok(self) -> "ValidationResult":
        if not self.ok:
            raise FactoryError("; ".join(self.errors) or "Factory result rejected")
        return self


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(value: str) -> str:
    allowed = set(string.ascii_letters + string.digits + "-_.")
    clean = "".join(ch if ch in allowed else "_" for ch in value.strip())
    return clean.strip("._") or "texture"


def _job_id(texture_name: str = "texture") -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"JOB_{stamp}_{_safe_name(texture_name)[:48]}"


def _save_png_exact(value: Path | str | Image.Image, destination: Path) -> tuple[int, int, str]:
    if isinstance(value, Image.Image):
        image = value.copy()
    else:
        image = Image.open(Path(value))
        image.load()
    # Preserve alpha when present.  Do not resize, resample, quantise, or palette-convert.
    if image.mode not in ("RGBA", "RGB", "LA", "L"):
        image = image.convert("RGBA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)
    width, height = image.size
    mode = image.mode
    image.close()
    return width, height, mode


def discover_google_drive_roots() -> list[Path]:
    """Return plausible Google Drive for desktop roots without touching OAuth.

    The explicit ``ALRUMMI3_FACTORY_ROOT`` / ``GOOGLE_DRIVE`` environment
    variables win.  On Windows we also inspect common user folders and mounted
    drive letters for a ``My Drive`` directory.  The caller still chooses the
    root; discovery never writes to a candidate path.
    """
    found: list[Path] = []

    def add(path: Path | str | None) -> None:
        if not path:
            return
        p = Path(path).expanduser()
        try:
            p = p.resolve()
        except OSError:
            pass
        if p.exists() and p not in found:
            found.append(p)

    explicit = os.environ.get("ALRUMMI3_FACTORY_ROOT")
    if explicit:
        p = Path(explicit).expanduser()
        if p.name.lower() == DEFAULT_FACTORY_NAME.lower():
            add(p.parent)
        else:
            add(p)

    add(os.environ.get("GOOGLE_DRIVE"))
    home = Path.home()
    for candidate in (
        home / "Google Drive" / "My Drive",
        home / "Google Drive",
        home / "My Drive",
    ):
        add(candidate)

    if os.name == "nt":
        for letter in string.ascii_uppercase:
            base = Path(f"{letter}:\\")
            try:
                if not base.exists():
                    continue
                my_drive = base / "My Drive"
                if my_drive.exists():
                    add(my_drive)
            except OSError:
                continue

    return found


def default_factory_root() -> Path | None:
    explicit = os.environ.get("ALRUMMI3_FACTORY_ROOT")
    if explicit:
        return Path(explicit).expanduser()
    roots = discover_google_drive_roots()
    if not roots:
        return None
    return roots[0] / DEFAULT_FACTORY_NAME


def build_prompt(
    *,
    job_id: str,
    texture_name: str,
    width: int,
    height: int,
    editable_regions: Sequence[Box],
    instructions: str = "",
) -> str:
    regions = "\n".join(
        f"- region {i + 1}: x={b.left} y={b.top} w={b.width} h={b.height}"
        for i, b in enumerate(editable_regions)
    ) or "- No reliable edit boxes were supplied; preserve all non-text artwork as exactly as possible."
    extra = instructions.strip() or "Rebuild only the Japanese/broken text/UI art that genuinely needs localization."
    return f"""ALRUMMI 3 IMAGE FACTORY JOB: {job_id}

You are producing a production replacement texture for Sengoku BASARA 3 Utage.
This is NOT a concept image and NOT a redesign.

Texture: {texture_name}
Required output: exactly {width} x {height} pixels, PNG, same atlas geometry.
Return filename: {RESULT_NAME}

NON-NEGOTIABLE RULES
1. Use source.png as the geometry/UV authority.
2. Use pristine_jpn.png (when present) to recover art damaged by earlier edits.
3. Use samurai_heroes.png (when present) as Capcom's official English style/reference, not as permission to move UVs.
4. Preserve dimensions, sprite positions, transparency, borders, icons, ornaments, and untouched artwork.
5. Do not crop, pad, rotate, upscale, downscale, or rearrange the atlas.
6. Replace only the intended text/art regions.  Everything else should remain pixel-identical wherever feasible.
7. English must look native to the original game: matching weight, outline, glow/shadow, spacing, baseline, and material treatment.
8. Do not patch an ARC.  Only return the full replacement PNG.
9. The Alrummi validator may reject changes outside the declared editable regions.

EDITABLE REGIONS
{regions}

JOB-SPECIFIC INSTRUCTIONS
{extra}

When finished, place the full-sheet PNG at OUTBOX/{job_id}/{RESULT_NAME} and, if possible, add result.json containing a short description of what changed.
"""


def create_job(
    config: FactoryConfig,
    source: Path | str | Image.Image,
    *,
    texture_name: str,
    metadata: dict[str, Any] | None = None,
    pristine_jpn: Path | str | Image.Image | None = None,
    samurai_heroes: Path | str | Image.Image | None = None,
    current_english: Path | str | Image.Image | None = None,
    ingame_mockup: Path | str | Image.Image | None = None,
    contact_sheet: Path | str | Image.Image | None = None,
    sprite_crops: Iterable[tuple[str, Path | str | Image.Image]] = (),
    editable_regions: Iterable[Any] = (),
    instructions: str = "",
    job_id: str | None = None,
) -> FactoryJob:
    """Create an atomic, reviewable Drive job.

    ``.ready`` is written last so a watcher never sees a half-written job.
    Existing job directories are refused rather than overwritten.
    """
    config.ensure()
    jid = job_id or _job_id(texture_name)
    inbox = config.inbox / jid
    outbox = config.outbox / jid
    if inbox.exists() or outbox.exists():
        raise FactoryError(f"Job already exists: {jid}")
    inbox.mkdir(parents=True)
    outbox.mkdir(parents=True)

    try:
        width, height, source_mode = _save_png_exact(source, inbox / "source.png")
        source_sha = _sha256_file(inbox / "source.png")
        files: dict[str, str] = {"source": "source.png"}

        refs = (
            ("pristine_jpn", pristine_jpn, "pristine_jpn.png"),
            ("samurai_heroes", samurai_heroes, "samurai_heroes.png"),
            ("current_english", current_english, "current_english.png"),
            ("ingame_mockup", ingame_mockup, "ingame_mockup.png"),
            ("contact_sheet", contact_sheet, "contact_sheet.png"),
        )
        for key, value, name in refs:
            if value is None:
                continue
            rw, rh, _ = _save_png_exact(value, inbox / name)
            # Full-sheet references must match.  Mockups/contact sheets may not.
            if key in {"pristine_jpn", "samurai_heroes", "current_english"} and (rw, rh) != (width, height):
                raise FactoryError(
                    f"{name} is {rw}x{rh}; full-sheet reference must match source {width}x{height}"
                )
            files[key] = name

        crop_dir = inbox / "sprites"
        crop_files: list[dict[str, str]] = []
        for index, (name, value) in enumerate(sprite_crops, 1):
            filename = f"{index:02d}_{_safe_name(name)}.png"
            _save_png_exact(value, crop_dir / filename)
            crop_files.append({"name": name, "file": f"sprites/{filename}"})

        boxes = tuple(Box.from_any(v).clamp(width, height) for v in editable_regions)
        boxes = tuple(b for b in boxes if b.width > 0 and b.height > 0)
        manifest: dict[str, Any] = {
            "schema": "alrummi3.chatgpt_factory",
            "schema_version": SCHEMA_VERSION,
            "job_id": jid,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
            "texture_name": texture_name,
            "source": {
                "width": width,
                "height": height,
                "mode": source_mode,
                "sha256": source_sha,
            },
            "files": files,
            "sprite_crops": crop_files,
            "editable_regions": [b.as_dict() for b in boxes],
            "expected_result": {
                "file": RESULT_NAME,
                "width": width,
                "height": height,
                "format": "PNG",
            },
            "validation": {
                "max_outside_change_ratio": config.max_outside_change_ratio,
                "pixel_difference_threshold": config.pixel_difference_threshold,
                "require_same_alpha_size": config.require_same_alpha_size,
            },
            "metadata": metadata or {},
        }
        prompt = build_prompt(
            job_id=jid,
            texture_name=texture_name,
            width=width,
            height=height,
            editable_regions=boxes,
            instructions=instructions,
        )
        (inbox / "prompt.md").write_text(prompt, encoding="utf-8")
        (inbox / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (outbox / "README_RETURN_HERE.txt").write_text(
            f"Place the finished full-sheet PNG here as {RESULT_NAME}.\n"
            f"It must be exactly {width}x{height}.\n",
            encoding="utf-8",
        )
        # Atomic-ish readiness marker: everything important is already durable.
        (inbox / READY_NAME).write_text("ready\n", encoding="ascii")
    except Exception:
        shutil.rmtree(inbox, ignore_errors=True)
        shutil.rmtree(outbox, ignore_errors=True)
        raise

    return FactoryJob(
        job_id=jid,
        inbox_dir=inbox,
        outbox_dir=outbox,
        manifest_path=inbox / "manifest.json",
        source_path=inbox / "source.png",
        width=width,
        height=height,
        editable_regions=boxes,
    )


def load_job(config: FactoryConfig, job_id: str) -> FactoryJob:
    inbox = config.inbox / job_id
    outbox = config.outbox / job_id
    manifest_path = inbox / "manifest.json"
    if not manifest_path.is_file():
        raise FactoryError(f"Missing manifest for job {job_id}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = data["expected_result"]
    boxes = tuple(Box.from_any(v) for v in data.get("editable_regions", ()))
    return FactoryJob(
        job_id=job_id,
        inbox_dir=inbox,
        outbox_dir=outbox,
        manifest_path=manifest_path,
        source_path=inbox / data.get("files", {}).get("source", "source.png"),
        width=int(expected["width"]),
        height=int(expected["height"]),
        editable_regions=boxes,
    )


def result_available(job: FactoryJob) -> bool:
    path = job.result_path
    if not path.is_file():
        return False
    try:
        # Avoid importing while Drive is still streaming the file.
        first = path.stat()
        if first.st_size < 64:
            return False
        with path.open("rb") as handle:
            header = handle.read(24)
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    except OSError:
        return False


def _outside_region_change_ratio(
    source: Image.Image,
    result: Image.Image,
    regions: Sequence[Box],
    threshold: int,
) -> tuple[float, int, int]:
    """Count materially changed pixels outside editable regions."""
    src = source.convert("RGBA")
    out = result.convert("RGBA")
    width, height = src.size
    if not regions:
        return 0.0, 0, width * height

    allowed = Image.new("1", (width, height), 0)
    # Pillow rectangle's end point is inclusive, so use right-1/bottom-1.
    from PIL import ImageDraw

    draw = ImageDraw.Draw(allowed)
    for box in regions:
        b = box.clamp(width, height)
        if b.width and b.height:
            draw.rectangle((b.left, b.top, b.right - 1, b.bottom - 1), fill=1)

    s = src.load()
    r = out.load()
    a = allowed.load()
    changed = 0
    checked = 0
    for y in range(height):
        for x in range(width):
            if a[x, y]:
                continue
            checked += 1
            if max(abs(int(s[x, y][i]) - int(r[x, y][i])) for i in range(4)) > threshold:
                changed += 1
    return (changed / checked if checked else 0.0), changed, checked


def validate_result(
    config: FactoryConfig,
    job: FactoryJob,
    result_path: Path | str | None = None,
) -> ValidationResult:
    path = Path(result_path) if result_path else job.result_path
    report = ValidationResult(ok=False, path=path)
    if not path.is_file():
        report.errors.append(f"Result does not exist: {path}")
        return report

    try:
        with Image.open(job.source_path) as source:
            source.load()
            with Image.open(path) as result:
                result.load()
                report.metrics["format"] = result.format
                report.metrics["mode"] = result.mode
                report.metrics["size"] = list(result.size)
                if result.format != "PNG":
                    report.errors.append(f"Result must be PNG, got {result.format or 'unknown'}")
                if result.size != (job.width, job.height):
                    report.errors.append(
                        f"Wrong dimensions: {result.width}x{result.height}; expected {job.width}x{job.height}"
                    )
                    return report

                source_rgba = source.convert("RGBA")
                result_rgba = result.convert("RGBA")
                source_alpha = source_rgba.getchannel("A")
                result_alpha = result_rgba.getchannel("A")
                if config.require_same_alpha_size:
                    # Do not require every alpha byte to match; text itself may legitimately
                    # change alpha.  Ensure the occupied alpha canvas has not been cropped/
                    # shifted away wholesale.
                    src_bbox = source_alpha.getbbox()
                    out_bbox = result_alpha.getbbox()
                    report.metrics["source_alpha_bbox"] = src_bbox
                    report.metrics["result_alpha_bbox"] = out_bbox
                    if src_bbox and out_bbox and src_bbox != out_bbox:
                        report.warnings.append(
                            f"Alpha occupied bounds changed from {src_bbox} to {out_bbox}; inspect before approval"
                        )

                diff = ImageChops.difference(source_rgba, result_rgba)
                extrema = diff.getextrema()
                changed_at_all = any(channel_max > 0 for _channel_min, channel_max in extrema)
                report.metrics["changed"] = changed_at_all
                if not changed_at_all:
                    report.warnings.append("Returned image is byte-visually identical to the source")

                if job.editable_regions:
                    ratio, changed, checked = _outside_region_change_ratio(
                        source_rgba,
                        result_rgba,
                        job.editable_regions,
                        config.pixel_difference_threshold,
                    )
                    report.metrics.update(
                        outside_changed_pixels=changed,
                        outside_checked_pixels=checked,
                        outside_change_ratio=ratio,
                    )
                    if ratio > config.max_outside_change_ratio:
                        report.errors.append(
                            "Too much artwork changed outside the approved edit regions: "
                            f"{ratio:.3%} > {config.max_outside_change_ratio:.3%}"
                        )

                # Cheap corruption/blank-image guard.
                stats = ImageStat.Stat(result_rgba)
                report.metrics["channel_mean"] = [round(v, 3) for v in stats.mean]
                if result_alpha.getbbox() is None:
                    report.errors.append("Result is fully transparent")
    except Exception as exc:
        report.errors.append(f"Cannot decode/validate result: {exc}")
        return report

    report.metrics["sha256"] = _sha256_file(path)
    report.ok = not report.errors
    return report


def write_validation_report(job: FactoryJob, report: ValidationResult) -> Path:
    target = job.outbox_dir / "validation.json"
    payload = {
        "job_id": job.job_id,
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "metrics": report.metrics,
        "result": str(report.path.name),
        "validated_utc": datetime.now(timezone.utc).isoformat(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def archive_job(config: FactoryConfig, job: FactoryJob, *, accepted: bool) -> Path:
    """Archive a completed job without overwriting an earlier archive."""
    destination_root = config.done if accepted else config.rejected
    destination = destination_root / job.job_id
    if destination.exists():
        raise FactoryError(f"Archive already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    for label, source in (("INBOX", job.inbox_dir), ("OUTBOX", job.outbox_dir)):
        if source.exists():
            shutil.move(str(source), str(destination / label))
    return destination


def candidate_image(job: FactoryJob, config: FactoryConfig) -> Image.Image:
    """Return a detached PIL image only after structural validation passes."""
    report = validate_result(config, job).require_ok()
    write_validation_report(job, report)
    with Image.open(job.result_path) as image:
        image.load()
        return image.convert("RGBA").copy()


__all__ = [
    "Box",
    "FactoryConfig",
    "FactoryError",
    "FactoryJob",
    "ValidationResult",
    "archive_job",
    "build_prompt",
    "candidate_image",
    "create_job",
    "default_factory_root",
    "discover_google_drive_roots",
    "load_job",
    "result_available",
    "validate_result",
    "write_validation_report",
]
