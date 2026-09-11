# Alrummi 3 — Drive-backed ChatGPT factory

This is the supported free-ChatGPT handoff path for high-quality texture artwork.
It does **not** use the OpenAI image API and does **not** allow a remote result to patch an ARC automatically.

## Live Drive queue

A persistent Google Drive folder is used as the interchange:

```text
Alrummi3_AI_Factory/
    INBOX/
        JOB_.../
            source.png
            pristine_jpn.png          (when available)
            samurai_heroes.png        (when available)
            current_english.png       (when available)
            ingame_mockup.png         (when available)
            contact_sheet.png         (when available)
            sprites/                  (detected sprite crops)
            prompt.md
            manifest.json
            .ready
    OUTBOX/
        JOB_.../
            replacement.png
            result.json               (optional)
            validation.json           (written by Alrummi)
    DONE/
    REJECTED/
```

The Drive root created for the project is:

- `Alrummi3_AI_Factory`
- Drive folder id: `1ygm3zvjYu31TDhxTgrroeBQxi67pPUW1`

Subfolder ids:

- INBOX: `1UyJzVTU2vnouzdMZChroqzefUSsXGY2z`
- OUTBOX: `17uAK37aeoAuikQUPXyCeNTCQI51pKP_D`
- DONE: `1OTqNxO2rpNJvCxA4zV8SPu0cbDcBxUIy`
- REJECTED: `1bqoA_R9NzwCq0hmHjIxM4IKhwdZAbrUE`

The IDs are documentation only.  The Windows build should normally use Google Drive for desktop and operate on the locally synced `Alrummi3_AI_Factory` directory like an ordinary filesystem folder.

## Trust boundary

The flow is deliberately split:

1. Alrummi exports source/reference material and a manifest.
2. Google Drive synchronizes it.
3. ChatGPT edits the image.
4. The finished full-sheet image is returned as `OUTBOX/<job>/replacement.png`.
5. Alrummi validates the result.
6. A valid result is loaded into the candidate pane.
7. **The user still approves the art before any ARC rebuild.**

A remote result must never call the ARC writer directly.

## Current code

`drive_factory.py`
: Creates jobs, discovers likely Drive Desktop roots, emits prompts/manifests, validates returned PNGs, and archives completed jobs.

`drive_factory_controller.py`
: Tk-friendly non-blocking controller.  It submits a job, polls OUTBOX, validates a returned PNG, and hands a detached PIL image to the GUI callback.

`drive_factory_selftest.py`
: Fast offline checks for exact dimensions, region-only changes, and rejection of unrelated atlas modifications.

## v31 GUI hook

The local `dist-v31` source is ahead of the GitHub GUI, so do not replace the local GUI with the older repository copy.  Hook the factory into the existing v31 `SEND TO CHATGPT` path with a narrow import:

```python
from drive_factory import FactoryConfig, default_factory_root
from drive_factory_controller import FactoryController
```

Create the controller once after Tk startup:

```python
factory_root = default_factory_root()
if factory_root is not None:
    self.drive_factory = FactoryController(
        FactoryConfig(factory_root),
        on_candidate=self._factory_candidate_ready,
        on_status=self._set_status,
    )
    self.drive_factory.watch(self)
else:
    self.drive_factory = None
```

The callback must only update the visual candidate:

```python
def _factory_candidate_ready(self, job, image, report):
    self.candidate_image = image
    self.candidate_meta = {
        "source": "chatgpt_drive_factory",
        "job_id": job.job_id,
        "validation": report.metrics,
    }
    self._refresh_previews()
```

The exact refresh function name may differ in v31.  Preserve the existing candidate/approval path rather than bypassing it.

When `SEND TO CHATGPT` is clicked, use the already-resolved full-size textures and layout information:

```python
job = self.drive_factory.submit(
    self.source_image,
    texture_name=self.selected_entry.name,
    metadata={
        "archive": str(self.archive.path),
        "resource": self.selected_entry.name,
        "format": "XET/BC3",  # use actual decoded metadata
    },
    pristine_jpn=self.reference_image,
    samurai_heroes=sh_image,
    current_english=self.source_image,
    ingame_mockup=mockup_image,
    contact_sheet=contact_sheet,
    sprite_crops=sprite_crops,
    editable_regions=approved_boxes,
    instructions=translation_and_art_direction,
)
```

Do not substitute thumbnails for any full-sheet source/reference argument.  The returned `replacement.png` must match the exact source dimensions.

## Result validation

The validator currently enforces:

- valid PNG
- exact original width/height
- not fully transparent
- alpha occupied-bounds warning
- optional strict editable-region containment
- SHA-256/report generation

If editable regions are known, pixels outside them are checked against the source.  This is intentional: an image generator that redraws the whole atlas must not silently become a production patch.

The default tolerance is conservative.  For sheets where a glow legitimately spills a few pixels outside a box, grow the approved box rather than weakening global validation.

## Cockpit rule

For cockpit assets, `SEND TO CHATGPT` should include whenever available:

- full selected atlas
- pristine JPN counterpart
- official Samurai Heroes counterpart
- current ENG state
- contact sheet of sprites
- individual text-bearing sprite crops
- owning LSP/controller metadata
- in-game/HUD mockup
- explicit editable boxes

This keeps ChatGPT from reviewing a mystery atlas in isolation.

## Free-tier limitation

Drive is the transport, not an unattended inference trigger.  A normal ChatGPT turn is still required to perform the image edit unless a separate API or UI-automation worker is introduced.  Alrummi can, however, make the return leg automatic: once `replacement.png` appears in OUTBOX, it is detected, validated, and loaded as a candidate without another file picker.
