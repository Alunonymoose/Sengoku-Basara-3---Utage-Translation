---
name: basara-texture-engineering
description: Mandatory workflow for BASARA/Utage ARC/TEX/XET texture sheets, atlases and UI repairs. Decode/prove live resources first, generate isolated art only, composite deterministically, approval-gate exact candidates, then encode and validate.
---

# Utage texture engineering

Apply the BASARA production contract first.

**Codec (2026-09-25, runtime-proven; constants confirmed in Capcom's own shaders 2026-09-26):** BC payloads use standard DXT byte order (no PS3 endpoint swap); 0x2A = BC3 + YCbCr, neutral chroma 123 (the game's `rShaderPackage` decodes with −123/255, 1.402, 0.34414, 0.71414, 1.772 — `project/texture_tools/GAME_SHADER_GROUND_TRUTH_2026-09-26.md`). Decode for review with `basara tex decode` (display space); write only via `basara tex arc-graft` / patchset texture ops. `xetenc.py`/`xet3.py` are quarantined. Canon: `project/texture_tools/TEXTURE_PIPELINE_CANON_2026-09-25.md`.

## Entry lock: decode before generate

If an ARC/TEX/XET is supplied or named, inspect/extract/decode the real live resource before custom generation.

“new texture sheet”, “make this nice”, “from scratch”, “fix this”, or “from menu.arc” still means a production-compatible edit of the proven live resource.

“From scratch” may replace art inside a proven edit region. It does not authorize changing atlas geometry, support fields, neighboring slots, frames or unrelated UI.

## Six-field generation gate

Before any creative generation explicitly establish:
1. `LIVE_INPUT` — current file identity/hash
2. `TARGET_MEMBER` — exact member index/path
3. `DECODED_SOURCE` — actual decoded live texture
4. `REAL_REFERENCE` — real JPN/SH/donor extraction or NONE
5. `EDIT_MASKS` — exact source-space rectangles/masks
6. `APPROVAL_REQUIRED` — true/false

If any field is unresolved, inspect first. Do not generate.

## Hard prohibition on whole-sheet generation

Generate only isolated lettering/art for one proven region.

Never use image generation to:
- redraw or improve an entire atlas/sheet
- recreate current ENG, pristine JPN, SH donor or another reference
- reproduce untouched pixels or neighboring slots
- invent frames/backgrounds/UI chrome
- build or beautify the approval board

If generation cannot satisfy the isolated shape cleanly, use deterministic drawing/compositing or a proven donor instead of escalating scope.

## Real-reference rule

Anything labeled current/JPN/SH/original/reference must come from real decoded bytes.
Generated reconstructions are concept studies only and cannot enter the production approval chain.

If a real reference is unavailable, obtain it or omit the panel. Never fabricate it.

## Exact candidate construction

Programmatically composite isolated art into a copy of the exact decoded live sheet.

Preserve:
- source dimensions and orientation
- slot coordinates and padding
- alpha/channel semantics
- material/debug-looking support fields
- every pixel/block outside frozen masks

BC edits must respect 4x4 boundaries where applicable.

The approval candidate is the exact full source-compatible sheet produced by that compositor.

Any screenshot/mockup must be derived from the candidate, never used as its source.

## Deterministic approval board

If useful, assemble the comparison with PIL/ImageMagick or equivalent from:
- real current decoded source
- real pristine JPN/SH/reference decode
- exact candidate

Do not call image generation for the comparison board.

## Candidate manifest gate

Before showing a custom candidate, write `candidate_manifest.json` with:
- source ARC/file SHA-256
- target member index/path
- source member hash
- reference hash where used
- decoded width/height/format
- edit mask rectangles
- candidate PNG hash
- `unchanged_outside_mask: true`
- `approval_required: true`
- `arc_patched: false`

Programmatically compare source and candidate outside masks.
Fail closed on any out-of-mask difference.

## Approval identity

Approval freezes the exact candidate pixels.
After approval route directly to encode/graft/rebuild; no creative tool call unless the user reopens approval.

## Known project constraints

Unless newer family evidence supersedes them:
- affected LSP logical coordinates may map to atlas physical coordinates at 2x
- BC3/DXT5 edits respect 4x4 blocks
- do not assume linear copy safety for RSX-swizzled/tiled data
- known gallery/UI shader cases use Green=opacity and Alpha=brightness
- XET v0x97 cases use the proven family header/orientation rules
- Kuriimu-dependent resources use the proven Capcom/Kuriimu transform, not a visually similar generic codec

## Final validation

After approval and encoding:
1. rebuild only the live ARC/member set allowed by the mutation budget
2. reparse the finished ARC
3. re-extract the texture from the finished ARC
4. decode that final stored texture
5. compare it to the approved candidate
6. verify protected ARC members remained unchanged
7. assign only the evidence level actually achieved

Do not validate only the pre-encode PNG.

For custom art, stop at the exact candidate until the user approves it.
