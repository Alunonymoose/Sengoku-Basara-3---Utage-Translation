# UtageStyleKitAssembler (v0)

Emits `(candidateRgba, editMask01)`. Does **not** write ARC bytes.
Caller wires the result into `UtageSingleEntryXetGraft.BuildSibling`.

## Tier order (highest wins)

| Tier | Condition | Production? |
|------|-----------|-------------|
| `ShPixelCrop` | `ShDonorRgba` set and `ShDonorMatcherConfidence >= 0.80` | Yes |
| `StyleKitV0` | `IStyleKitV0` supplied | Yes, labeled v0 |
| `MockupBlocked` | No donor, no kit, `production:false` | **No** — never call `BuildSibling` |

`production:true` with no donor and no kit **throws**. Desktop text is never emitted as a production candidate.

## SH confidence adapter

`ShDonorMatcherConfidence` is **not** produced by `ReferenceMatcher` directly.

`ReferenceMatcher` yields `ReferenceMatch` with `ReferenceMatchConfidence`
(`Candidate` / `Strong` / `ExactLanguageVariant`) and a `Score`.

The **App boundary** is responsible for:

1. Calling `TryResolveUniqueStrong` (never auto-pick `Candidate`).
2. Only populating `ShDonorRgba` when that returns non-null.
3. Setting `ShDonorMatcherConfidence = 1.0f` for Strong / ExactLanguageVariant.

The assembler does not call the matcher; it trusts the caller to have gated.

## What StyleKitV0 is (and is not)

- **Is**: stroke dilation + vertical fill gradient + upper-left outer bevel + lower-right inner bevel.
- **Is not**: Capcom-certified metal-jade roulette lettering.
- **Ships with**: `SyntheticStyleKitV0` (5×7 bitmap font) for CI only.

## Mask and block footprint

Assembler emits an **exact-delta** mask: `mask01[i] = 1` iff candidate pixel differs from pristine.

`UtageBc3BlockGraft.MaskToBlockSet` expands to intersecting 4×4 BC3 blocks.
`CountOutsideMaskDeltas` must return 0 or `Assemble` throws.

## Multi-line

Lines split on `\n`. Line height = `BoxHeight / lineCount`.
Scale fits **line height first**, then shrinks if width overflows.
This avoids the "caption floating in empty card" underfill failure.

## Production path

```
pristine decode RGBA
  -> UtageStyleKitAssembler.Assemble(...)
  -> candidateRgba + mask01
  -> UtageSingleEntryXetGraft.BuildSibling(sourceArc, memberIndex, pristineXet, candidateRgba, mask01)
```

`ReplaceSingleLevel` is **not** used as a production writer.

## Non-goals

- No new production writer / parallel `IUtageGraftWriter`
- No full-sheet production encode
- No Alrummi / Tk / Drive handoff
- No writes under ENG/JPN game roots
- No public `AssetApprovalEvidence` factory

## Smoke

```bash
dotnet run --project tests/BasaraFoundry.StyleKitSmokeTests/BasaraFoundry.StyleKitSmokeTests.csproj -c Release
```
