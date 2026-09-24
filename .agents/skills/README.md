# BASARA Utage Agent Skills

This directory contains the reusable engineering skills for the Sengoku BASARA 3 Utage PS3 English localisation project and BASARA Foundry.

These files are intended to stop future agents from rediscovering the same format/workflow facts and from regressing known safety rules.

## Skills

### `basara-utage-core`

Use for any substantial Utage work, project continuation, source-of-truth recovery, ownership/routing, handoff, or when deciding which specialist skill applies.

Primary role: project operating system.

Path:

`.agents/skills/basara-utage-core/SKILL.md`

### `basara-utage-texture-engineering`

Use for ARC/TEX/XET/BC texture work, 0x2B/RBxG, UI atlases, title/gallery/panel textures, shared-owner texture rebuilds, and texture/layout verification.

Primary role: safe production texture pipeline.

Path:

`.agents/skills/basara-utage-texture-engineering/SKILL.md`

### `basara-utage-research`

Use for reverse engineering, unknown binary fields, forensic audits, public-source comparison, cross-game evidence, hypothesis testing, and external-agent research handoffs.

Primary role: evidence discipline and canon promotion.

Path:

`.agents/skills/basara-utage-research/SKILL.md`

## Routing examples

- "Continue the Utage patch" -> core
- "Fix this title.arc texture" -> core + texture engineering
- "Why does format 0x2B render strangely?" -> texture engineering + research if semantics are unresolved
- "Audit DeepSeek's claim about ARC compression" -> research
- "Patch an approved atlas back into the game" -> texture engineering
- "Find the real owner of this texture" -> core, then texture engineering if a texture change follows
- "Compare Sumeragi's implementation" -> research; do not import it as canon automatically

## Precedence

1. User's explicit current request
2. Current real Utage evidence and current repository implementation/tests
3. Current BASARA Foundry Drive canon/checkpoints
4. These skills
5. Older project notes/memory
6. Generic MT Framework knowledge

If a skill conflicts with newer fixture-backed evidence, update the skill rather than forcing the project to follow stale text.

## Source-of-truth locations

Code/history:

`Alunonymoose/Sengoku-Basara-3---Utage-Translation`

Primary production engineering branch:

`foundry-v0.1`

Current orchestration integration branch (until reviewed/merged):

`foundry-v0.2-orchestration`

Canonical project memory:

Google Drive `BASARA Foundry`

Mandatory Drive startup documents when available:

1. `00 READ ME FIRST — BASARA FOUNDRY / UTAGE MASTER SOURCE OF TRUTH`
2. `01 UTAGE TECHNICAL CANON — FORMATS, ROUTING, WORKFLOW, PROVEN FAILURES`

## Current hardening note — 2026-09-17

A separate texture-pipeline hardening change-set established/validated the following rules and should be considered when reconciling these skills with the live branch:

- normal incremental texture edits preserve the current live target payload outside touched blocks
- pristine Japanese payload is only an explicit restore/repair base
- format `0x2B` requires RBxG-aware handling and must not be treated as ordinary artist RGBA
- format `0x15` should fail closed until exact semantics are fixture-proven
- unexplained non-zero ARC gaps/trailers should fail closed rather than be destroyed
- shared-owner build evidence must bind the complete owner/output set

Always inspect the latest branch/PR/checkpoint before production work.

## Runtime-verified title 0x2A closure — 2026-09-18

The `title_004_ID_HQ` Sengoku repair is no longer an open research problem. The exact PS3 0x2A YCbCr channel contract and the clean-edge reconstruction used by the accepted title build are recorded in `basara-utage-texture-engineering/SKILL.md` and the supporting file `TITLE_0x2A_RUNTIME_VERIFIED_2026-09-18.md`.

Future agents must recover that record before title-logo XET work and must not restart from generic RGBA assumptions, global neutral-chroma experiments, or stale pre-2026-09-18 title notes.

## Keeping skills current

When a discovery changes engineering behavior:

1. patch/test the implementation
2. update the relevant `SKILL.md`
3. update the Drive canon/checkpoint
4. record what old rule was superseded

Do not allow Skills, Drive canon, and Foundry code to silently drift apart.

## Foundry v0.2 machine-truth rule — 2026-09-24

For current-live byte/ownership claims, the latest verified v0.2 snapshot outranks prose handoffs. Exact resource identity is type hash + ASCII-lowercased internal path. Runtime rendering/precedence claims remain evidence-bound. Patch approvals are candidate-SHA-bound and become stale if the live snapshot/provider hashes change.
