---
name: basara-production
description: Core production contract for Sengoku BASARA 3 Utage localisation. Apply before any mutation, texture generation, ARC rebuild, QA or delivery.
---

# BASARA production contract

## Source authority

Fresh/current E: bytes are LIVE MASTER and win for mutation.
Current project docs and skills guide architecture but never substitute for live production bytes.
Samurai Heroes and pristine JPN assets are references/donors.
Historical backups/checkpoints are evidence only unless explicitly promoted.

Never ask for a file already present and usable in the active task.

## Task fidelity

Deliver the requested thing, not an easier proxy:
- patch/fix/rebuild/root-ready -> actual binary/archive output
- texture/atlas repair -> exact source-compatible candidate
- QA -> direct inspection and evidence-backed findings
- owner/location -> concrete path/provider evidence
- runtime diagnosis -> discriminating test/evidence

Do not replace engineering output with a mockup or explanation when the environment can do the work.

## Immutable production states

Keep these distinct:
`LIVE_INPUT -> DECODED_SOURCE -> PROVEN_EDIT_REGION -> CANDIDATE -> APPROVED_CANDIDATE -> ENCODED_RESOURCE -> FINAL_ARC -> VALIDATED_ARTIFACT -> ROOT_READY -> RUNTIME_TESTED`

Never upgrade evidence status without proof.

## Creative-tool fail-closed gate

For in-game texture/UI/atlas work, no creative generation until all six are established:
1. LIVE_INPUT
2. TARGET_MEMBER
3. DECODED_SOURCE
4. REAL_REFERENCE
5. EDIT_MASKS
6. APPROVAL_REQUIRED

Image generation is allowed only for isolated art fitting frozen edit masks.
Never generate an entire production sheet, current/JPN/SH reference, untouched atlas pixels, or an approval board.

The exact candidate must be deterministically composited onto the real decoded source.

## Candidate proof

Before presenting a custom texture candidate, produce or be able to produce:
- source ARC/file SHA-256
- target member index/path
- decoded dimensions/format
- exact edit masks
- candidate SHA-256
- proof `unchanged_outside_mask: true`

Reject any candidate with unexplained pixels outside the allowed mask.

## Approval lock

User approval freezes the exact candidate pixels/bytes.
After approval do not regenerate, restyle, recolour, sharpen or reinterpret them unless approval is explicitly reopened.

## Mutation lock

Define the smallest permitted mutation set. Everything else is protected.
After rebuilding, reparse and re-extract the final artifact and compare protected content.
Unexplained drift is failure.

## Evidence language

Use only:
`HYPOTHESIS | STRUCTURALLY VERIFIED | VISUALLY VERIFIED | RUNTIME OBSERVED | RUNTIME PROVEN`

Do not call a workspace intermediate or static mockup “fixed.”
