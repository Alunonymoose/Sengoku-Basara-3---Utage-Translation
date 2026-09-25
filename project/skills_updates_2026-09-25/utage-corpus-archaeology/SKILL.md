---
name: "utage-corpus-archaeology"
description: "Run the Sengoku BASARA 3 Utage texture + dialogue corpus pass: classify every remaining text-bearing texture and every dialogue line against Samurai Heroes (official English reuse vs new work), emit candidates and a small review queue. Use when asked to finish/map the remaining localisation work."
---

# Utage — texture + dialogue corpus archaeology

Source tasking: Drive `BASARA Foundry — Frontier AI Tasking for Remaining Texture & Dialogue Work — 2026-09-25`
(id `1ntDiLxCXxgQCLXgzMh0oN8wCWTuc6ILxl3re032dmnE`). Read it in full first; it wins over this summary.

**Mission:** exhaust the ACTUAL remaining corpus. Success = coverage, not code. Keep going until every
text-bearing texture and every dialogue line is classified. Do not stop after writing tools.

## Data (needs the real files — run on the laptop, or have the user upload zips)
- Utage live: `E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng` (+ `rom\jpn`, not pristine)
- Samurai Heroes: `E:\SAMURAI HEROES` (official English + Japanese)

## Use existing decoders — do not write new parsers
`pip install -e project/basara` then: `basara arc ls`, `basara msg tables|show|census`,
`basara tex arc-list|decode|census`, and in Python `basara.arc`, `basara.msg`, `basara.font`,
`basara.markup`, `basara.xet`. Small throwaway analysis scripts on top are fine.

## Texture track → `texture_atlas.csv/json`
Every text-bearing Utage texture: logical asset, proven physical owners, display-space decode, SH donor
(visual/semantic match, not filename), class `EXACT_OFFICIAL_DONOR | PARTIAL_OFFICIAL_DONOR | NEEDS_NEW_ART |
NON_TEXT | INTENTIONAL_VARIANT | UNSUPPORTED_FORMAT | UNRESOLVED`, format + write-certification state,
candidate path, evidence still needed. 0x2A = BC3 + YCbCr (standard byte order); 0x15/0x2B/multi-mip write = fail closed.

## Dialogue track → `dialogue_reconciliation.csv/json`
Every Utage unit (RID, JP, speaker/scenario/context, control codes): exact source match to SH JP → official EN;
then sequence/context/semantic matching for moved/split/merged/rewritten lines. Class `OFFICIAL_EXACT_REUSE |
OFFICIAL_CONTEXT_VERIFIED_REUSE | OFFICIAL_ADAPTATION_REQUIRED | UTAGE_ONLY_NEW_TRANSLATION | CHANGED_SOURCE_REVIEW |
CONTROL_OR_NON_DIALOGUE | UNRESOLVED`. Never reuse official English because it merely looks close — if the Utage JP
changed, surface it. Candidates keep every control code (`basara.markup` tags) and SH terminology/voice.

## Also emit
`remaining_work.md` (exact counts + %, ready-to-install work, review queue, blocked queue — no vague TODOs),
`candidate_outputs/` (safe candidates only, no guessed binaries), `analysis_tools/` (only scripts actually used).
Write results to `E:\Utage Patching New\_CORPUS_ATLAS_<date>\` (never inside `rom\`) and summarise to Drive.

## Rules
No Foundry refactors, no platforms. No parent/child inheritance assumptions; no propagation without proof.
No merging units because JP text is identical. No quarantined encoders. Don't overwrite intentional variants.
Encoder↔decoder self-agreement is not validation. Nothing is runtime-verified without runtime evidence.
