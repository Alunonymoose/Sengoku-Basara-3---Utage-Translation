# SENGOKU BASARA 3 UTAGE — CLAUDE CODE PRODUCTION GATE

You are operating inside the live Sengoku BASARA 3 Utage English-localisation workspace.

## Authority order

1. Files under `E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng` are LIVE MASTER for mutation.
2. Fresh files explicitly supplied by the user for a task override older copies.
3. This repository's `.claude/skills/` and current project docs define the working engineering rules.
4. Samurai Heroes and pristine JPN resources are REFERENCES/donors, not automatic live replacements.
5. Historical backups, Drive copies, reports and old workspaces are evidence only unless explicitly promoted.

Never silently replace live E: bytes with an older backup/reference.

## Mandatory task routing

For any ARC/TEX/XET/atlas/UI/texture request, read and apply:
- `.claude/skills/basara-production/SKILL.md`
- `.claude/skills/basara-texture-engineering/SKILL.md`
- `.claude/skills/basara-arc-engineering/SKILL.md`

For QA/audit work also use:
- `.claude/skills/basara-qa/SKILL.md`

Byte-level work (ARC, XET, GSM/FIM/TNF/CSA, PSL) goes through `project/basara` (`pip install -e project/basara`; `basara arc|msg|tex|build|install`). Do not write new parsers, encoders or rebuild scripts.

Texture codec (runtime-proven 2026-09-25): standard BC byte order, 0x2A = BC3 + YCbCr; `xetenc.py`/`xet3.py` are quarantined. Canon: `project/texture_tools/TEXTURE_PIPELINE_CANON_2026-09-25.md`.

Remaining-work priority (2026-09-26): texture + dialogue corpus pass, not new architecture — `project/skills_updates_2026-09-25/utage-corpus-archaeology/SKILL.md`.

Do not treat this project as generic image generation or generic MT Framework modding.

## Production states

Keep these states distinct:

`LIVE_INPUT -> DECODED_SOURCE -> PROVEN_EDIT_REGION -> CANDIDATE -> APPROVED_CANDIDATE -> ENCODED_RESOURCE -> FINAL_ARC -> VALIDATED_ARTIFACT -> ROOT_READY -> RUNTIME_TESTED`

Never call a mockup a candidate, a candidate approved, or a static decode runtime proof.

## Texture hard gate

Before any custom image generation establish:
- LIVE_INPUT
- TARGET_MEMBER
- DECODED_SOURCE
- REAL_REFERENCE
- EDIT_MASKS
- APPROVAL_REQUIRED

Image generation may create isolated art only for a proven edit region.
It must never redraw a whole production atlas, recreate untouched pixels, fabricate a JPN/SH reference, or generate an approval board.

The exact candidate must be built deterministically on a copy of the real decoded live sheet.
Any comparison board must be assembled deterministically from real current/reference/candidate images.

For custom art, stop for user approval before encoding or ARC patching.

## Preservation and validation

Define the smallest mutation budget before editing. Everything else is protected.

For texture candidates produce a machine-readable manifest containing at minimum:
- source ARC/file hash
- target member index/path
- decoded dimensions/format
- edit masks
- candidate hash
- `unchanged_outside_mask: true`

If the unchanged-outside-mask check fails, reject the candidate.

After approval, approved candidate pixels are immutable: no restyling, regeneration, sharpening or creative reinterpretation during encoding.

After rebuilding an ARC, reparse it, re-extract the changed member, decode the final stored resource, and compare protected members to the live baseline.

**USER HARD RULE (2026-09-25): no ROOT-READY ZIPs.** Install directly on live E: only after a hash-verified backup of every ARC being changed (`basara install <build> --root <rom/eng> --backup-root <dir>`: verified backup, hash-guarded atomic write, read-back, INSTALL_RECORD.json; `basara rollback` never erases later edits).

## Behaviour

Do the work directly when the files are available. Do not send the user on preprocessing/export rabbit holes that can be done here.
Do not rediscover solved project architecture from generic knowledge.
Prefer real byte evidence, layout links, hashes, diffs and runtime tests.
When uncertain, fail closed on the exact unresolved fact rather than inventing a proxy.
