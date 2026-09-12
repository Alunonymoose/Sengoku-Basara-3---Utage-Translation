# Foundry vertical slice status — 2026-09-12

Branch: `foundry-v0.1`

## What is certified end-to-end

Operator path for **one texture member**:

1. **Index ENG** via worker `index --route eng`
2. **Select texture** → worker `preview-xet` (Current ENG pane)
3. **Resolve unique JP** via `ReferenceMatcher.TryResolveUniqueStrong` on JPN index  
   - Ambiguous / missing → production reference is **not** set (fail closed)
4. **Load candidate PNG** (exact WxH, content-addressed RGBA cache)
5. **Preview round-trip** (optional) via worker `roundtrip-xet` — full-sheet encode is **preview only**
6. **Edit mask proposal** from pristine JP decode vs candidate (`UtageEditMaskProposalService`)
7. **Operator reviews** exact pixels (magenta) vs BC3 collateral (amber)
8. **Build** via worker `graft-xet`:
   - pristine XET from **distinct JPN root/archive**
   - candidate RGBA + approved mask
   - `UtageSingleEntryXetGraft.BuildSibling` (mandatory pristine, schema 3 audit)
   - output **outside** ENG/JPN roots (`builds/texture-grafts/...`)
9. App re-verifies audit hashes vs frozen review bindings
10. **Runtime evidence** attachment is a separate build-bound gate (`RUNTIME_EVIDENCE.md`)

## Safety properties that must not regress

| Rule | Where enforced |
|------|----------------|
| Canonical sources read-only | Worker path checks + App build dir |
| Pristine art base is JP counterpart | `BuildSibling` requires non-empty pristine; worker rejects same root |
| Outside-mask identity | `UtageBc3BlockGraft` |
| Untouched ARC members | `UtageArcWriter.VerifyRebuiltArchive` |
| Approval proof not UI-forgeable | `AssetApprovalEvidence` internal ctor + `InternalsVisibleTo` Game.Utage only |
| Full-sheet encode not production | Round-trip service / `ReplaceSingleLevel` preview-only |

## CI smoke coverage

- Route resolution
- Reference matching
- BC3 round-trip (preview)
- BC3 block-graft + single-entry transaction
- Runtime evidence binding

WinUI publish is a separate CI job after core smokes.

## What is still **not** Foundry's job (yet)

- **Generating** Capcom-quality lettering / medallion fills  
  Foundry **consumes** a finished candidate RGBA. Style kits / glyph materials / SH pixel crop still live in research + Alrummi knowledge, not as a certified Foundry writer.
- Private `roulette_000_ID_HQ` fixture in CI (needs secret/private artifact policy)
- Batch multi-member ARC builds
- MSG text pipeline

## Recommended next product slice

1. **Style-kit candidate assembler** (Foundry service, not Tk): composite operator text or SH donor glyphs onto **decoded pristine JP** outside the mask, emit candidate RGBA for the existing review path.
2. Keep production write path unchanged — only improve what enters step 4.
3. Optional: gated private-fixture job once fixture hosting is decided.

## Tandem note

GPT closed the production wire-up (mask UI, worker `graft-xet`, mandatory JP, runtime evidence). Grok's earlier P0s are absorbed. Further work should not reopen Alrummi ChatGPT/Drive as a production dependency.
