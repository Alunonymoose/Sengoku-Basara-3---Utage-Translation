> **2026-09-26 CURRENT RULE:** this document previously mandated pristine-JPN as the normal production base. That is superseded. Current incremental production uses the CURRENT LIVE TARGET as shell and untouched-block base; pristine/JPN is reference or explicit `restore` input only. Use the current `.agents/skills/basara-utage-texture-engineering/SKILL.md` and Worker `--base-mode current|restore`.

# BC3 block-graft production writer

Status: implemented in `BasaraFoundry.Game.Utage.Xet.UtageBc3BlockGraft` (2026-09-12).

## Current rule

1. Do not production-reencode an entire BC3 atlas for lettering-only edits.
2. Use the **current live target XET** as the normal preservation base. Use pristine/reference payload only in explicit restore mode.
3. Candidate RGBA must be pixel-identical to the selected preservation-base decode outside the edit mask.
4. Expand the mask to intersecting 4×4 blocks; replace only those 16-byte BC3 blocks.
5. Preserve the current target XET shell/non-payload bytes and untouched compressed blocks byte-for-byte.
6. Decode the encoded candidate before approval; freeze approved encoded/touched-block bytes and reuse them in final production.
7. `UtageXetCodec.ReplaceSingleLevel` remains **preview / full-sheet evidence only**.

## API

```csharp
var result = UtageBc3BlockGraft.GraftTopLevel(currentTargetXet, candidateRgba, editMask01);
// result.Report.Ok must be true before any ARC writer sees result.XetBytes
```

## Smoke

`tests/BasaraFoundry.GraftSmokeTests` — synthetic 16×8 atlas, one block replaced, reject path for outside-mask edits.

## GPT tandem note

Next: wire graft output into ARC single-entry rebuild with `UtageArcWriter`, then roulette_000 private fixture when available. Do not promote full-sheet encode to production.
