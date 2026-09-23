# BC3 block-graft production writer

Status: implemented in `BasaraFoundry.Game.Utage.Xet.UtageBc3BlockGraft`.

## Production rule

1. Do not production-reencode an entire BC3 atlas for a localised edit.
2. Use the **current live target compressed payload** as the normal incremental preservation base.
3. Keep pristine JP as structural/reference evidence; use it as the untouched-art base only in explicit restore mode.
4. Expand the exact approved pixel mask to intersecting 4×4 blocks.
5. Candidate differences in untouched blocks are ignored because those blocks are never imported.
6. Candidate differences inside a touched block but outside the exact approved mask fail closed.
7. Encode the candidate in the correct artist/display semantics for the XET format.
8. Import only the selected 16-byte BC3 blocks.
9. Prove every untouched compressed block is byte-identical to the chosen preservation base.
10. Decode the final XET in display space and prove no pixel delta outside the effective touched-block mask.

## Format-aware editing

### Plain BC3

0x17/0x18 currently use direct RGBA -> BC3 on certified linear single-level fixtures.

### 0x2A

0x2A uses the dedicated PS3 MT Framework YCbCr editing path:

`display RGBA -> (Cr, alpha, Cb, Y) stored RGBA -> BC3`

Verification decodes BC3 stored channels and then applies the inverse YCbCr display shader before visual/pixel comparison.

Current compressor backend: `BCnEncoder.Net BcEncoder / BC3 BestQuality / mipmaps disabled`. This backend is not yet independently runtime-certified against the accepted `title_004` build; the runtime evidence certifies the 0x2A transform + surgical graft method, not an unnamed compressor implementation. Every production audit records the backend string so future runtime evidence can bind the exact encoder.

### 0x2B

Kuriimu2 applies the same YCbCr display shader, and the project's older RBxG representation is a lossless decomposition of those stored channels. Production writes remain fail-closed until a real Utage 0x2B fixture passes the full transaction and runtime gate.

### 0x15

No certified BC2/BC3 interpretation; fail closed.

## API

```csharp
var result = UtageBc3BlockGraft.GraftTopLevel(
    liveTargetXet,
    approvedDisplayRgba,
    editMask01);

if (!result.Report.Ok)
    throw new InvalidOperationException("Texture graft failed.");
```

The explicit pristine-restore mode is selected one layer up by `UtageSingleEntryXetGraft`, which chooses the graft base intentionally.

## Required report fields

At minimum preserve:

- total blocks;
- replaced/touched blocks;
- touched block coordinates;
- exact mask pixel count;
- candidate outside-mask delta;
- final outside-effective-block delta;
- BC compression collateral inside touched blocks.

## Smoke/regression intent

Generic graft infrastructure fixtures use ordinary BC3 so they do not accidentally bless special 0x2A semantics.

A separate YCbCr regression verifies the exact 0x2A transform and confirms that generic writers refuse 0x2A/0x2B and ambiguous 0x15.
