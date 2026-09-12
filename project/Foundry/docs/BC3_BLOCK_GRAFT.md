# BC3 block-graft production writer

Status: implemented in `BasaraFoundry.Game.Utage.Xet.UtageBc3BlockGraft` (2026-09-12).

## Rule (Research Ledger)

1. Do not production-reencode an entire BC3 atlas for lettering-only edits.
2. Use the pristine compressed payload (usually Japanese XET) as the artwork base.
3. Candidate RGBA must be pixel-identical to the pristine decode outside the edit mask.
4. Expand the mask to intersecting 4×4 blocks; replace only those 16-byte BC3 blocks.
5. Verify untouched compressed blocks remain byte-identical.
6. `UtageXetCodec.ReplaceSingleLevel` remains **preview / full-sheet evidence only**.

## API

```csharp
var result = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidateRgba, editMask01);
// result.Report.Ok must be true before any ARC writer sees result.XetBytes
```

## Smoke

`tests/BasaraFoundry.GraftSmokeTests` — synthetic 16×8 atlas, one block replaced, reject path for outside-mask edits.

## GPT tandem note

Next: wire graft output into ARC single-entry rebuild with `UtageArcWriter`, then roulette_000 private fixture when available. Do not promote full-sheet encode to production.
