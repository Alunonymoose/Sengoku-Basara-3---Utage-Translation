"""Small Tk-friendly controller for the Alrummi 3 Drive factory.

The controller intentionally knows nothing about ARC writes.  A GUI supplies:
- an image and references when submitting a job;
- a Tk object exposing ``after`` / ``after_cancel``;
- a callback that receives the validated PIL candidate.

That keeps the online handoff outside the archive-writing trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from drive_factory import (
    FactoryConfig,
    FactoryJob,
    ValidationResult,
    create_job,
    result_available,
    validate_result,
    write_validation_report,
)


StatusCallback = Callable[[str], None]
CandidateCallback = Callable[[FactoryJob, Image.Image, ValidationResult], None]
RejectCallback = Callable[[FactoryJob, ValidationResult], None]


@dataclass
class FactoryController:
    config: FactoryConfig
    on_candidate: CandidateCallback
    on_status: StatusCallback | None = None
    on_rejected: RejectCallback | None = None
    poll_ms: int = 1500

    def __post_init__(self) -> None:
        self.current_job: FactoryJob | None = None
        self._tk_owner: Any | None = None
        self._after_id: Any | None = None
        self._delivered_job_id: str | None = None

    def status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def submit(
        self,
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
    ) -> FactoryJob:
        job = create_job(
            self.config,
            source,
            texture_name=texture_name,
            metadata=metadata,
            pristine_jpn=pristine_jpn,
            samurai_heroes=samurai_heroes,
            current_english=current_english,
            ingame_mockup=ingame_mockup,
            contact_sheet=contact_sheet,
            sprite_crops=sprite_crops,
            editable_regions=editable_regions,
            instructions=instructions,
        )
        self.current_job = job
        self._delivered_job_id = None
        self.status(
            f"ChatGPT factory job {job.job_id} is ready in Drive. "
            f"Watching OUTBOX for replacement.png…"
        )
        return job

    def watch(self, tk_owner: Any) -> None:
        """Start non-blocking polling using Tk's event loop."""
        self._tk_owner = tk_owner
        self._schedule()

    def stop(self) -> None:
        if self._tk_owner is not None and self._after_id is not None:
            try:
                self._tk_owner.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = None
        self._tk_owner = None

    def poll_once(self) -> bool:
        """Return True only when a new valid candidate is delivered."""
        job = self.current_job
        if job is None or self._delivered_job_id == job.job_id:
            return False
        if not result_available(job):
            return False

        report = validate_result(self.config, job)
        write_validation_report(job, report)
        if not report.ok:
            self.status(
                "ChatGPT factory result rejected: " + "; ".join(report.errors)
            )
            if self.on_rejected:
                self.on_rejected(job, report)
            # Do not mark delivered: replacing replacement.png with a corrected
            # result should be picked up on a later poll.
            return False

        with Image.open(job.result_path) as opened:
            opened.load()
            candidate = opened.convert("RGBA").copy()
        self._delivered_job_id = job.job_id
        self.status(
            f"Validated {job.job_id}. Loaded returned PNG as candidate; "
            "ARC remains untouched until explicit approval."
        )
        self.on_candidate(job, candidate, report)
        return True

    def _schedule(self) -> None:
        if self._tk_owner is None:
            return
        self._after_id = self._tk_owner.after(self.poll_ms, self._tick)

    def _tick(self) -> None:
        try:
            self.poll_once()
        finally:
            self._schedule()


__all__ = ["FactoryController"]
