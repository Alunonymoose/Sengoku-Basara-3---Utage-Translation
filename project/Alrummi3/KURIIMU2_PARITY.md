# Alrummi 3 Next — Kuriimu2 parity notes

This overhaul treats Kuriimu2 as the format-behaviour reference for MT Framework PS3 textures, rather than trying to infer the final displayed image from raw BC blocks.

Upstream reference: `FanTranslatorsInternational/Kuriimu2`, especially:

- `plugins/Capcom/plugin_mt_framework/Images/MtTexSupport.cs`
- `plugins/Capcom/plugin_mt_framework/Images/MtTex.cs`
- `src/lib/Kanvas/Swizzle/BCSwizzle.cs`
- `src/lib/Kanvas/Swizzle/MasterSwizzle.cs`

Kuriimu2 is GPLv3. Alrummi's implementation is a Python reimplementation of the documented behaviour and formulas, not a bundled Kuriimu2 binary.

## Important correction to the old Alrummi 3 handoff

The old viewer decoded the compressed BC payload and displayed its RGBA channels directly. That is not sufficient for PS3 format `0x2A`.

Kuriimu2's PS3 encoding table maps `0x2A` to DXT5 and then applies `MtTex_YCbCrColorShader`. The stored DXT5 channels are effectively a packed colour representation:

- stored G -> displayed alpha
- stored A -> Y
- stored B - 123 -> Cb
- stored R - 123 -> Cr

The display RGB is reconstructed with the normal JPEG-style YCbCr equations. Kuriimu2 applies the inverse equations before writing.

This explains the characteristic green/magenta-looking raw preview in old Alrummi 3: it was showing the storage channels, not the final texture colour.

`alphaFlags` may still have game-specific meaning, but it was not the explanation for this colour mismatch.

## PS3 format table used by Next

The strict Kuriimu2 table is:

- `0x13` DXT1
- `0x14` DXT3
- `0x17` DXT5
- `0x19` DXT1
- `0x1F` DXT5
- `0x21` DXT5 + no-alpha display shader
- `0x27` DXT5
- `0x2A` DXT5 + MT YCbCr shader

The Utage project has additionally observed `0x15`, `0x18`, and `0x2B`. Next keeps those as explicitly-labelled compatibility cases rather than silently treating every unknown format as DXT5.

## Editing rule

All GUI editing happens in **display space**. For a `0x2A` texture, the write path converts the reviewed display-space candidate back through the inverse MT YCbCr transform before BC3 encoding.

Only BC blocks intersecting the changed rectangle are replaced at the top mip. Lower mips are regenerated only for the corresponding changed area. Unrelated atlas blocks remain byte-identical wherever possible.

## Native art rule

Alrummi Next does not use the old Gold/Jade/Bronze material presets as a localization default. Existing Utage artwork should be preserved. Translation work should prefer, in order:

1. an exact official Samurai Heroes donor;
2. surgical donor-region transplant;
3. lettering-only cleanup/rebuild inside a tight box;
4. imported, human-reviewed replacement art.

Generic procedural restyling is not considered a native-quality localization method.
