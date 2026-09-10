# Utage handover addendum — V20 compensated dialogue-text baseline

Date: 2026-08-31

## Runtime result after V19

V19's two SH special-root enable flags did not visibly move the text. Pixel
measurement of the supplied V18 and V19 three-line frames found identical glyph
bands. Against the official 1920x1080 SH two-line frame, Utage's first glyph row
began 12 pixels too low (`704` versus `692`).

The cockpit is authored in a 1280x720 coordinate space, so 12 output pixels at
1080p equals exactly 8 LSP units.

## V20 implementation

The character-dialogue tree in `cockpit1P.arc` is:

- parent `3`, stable ID 71 — generated-text anchor
- visual child `3_0`, stable ID 72 — portrait/name/dialogue plate
- visual child `3_1`, stable ID 76 — auxiliary strip/line visuals

V20 raises only the parent-level text origin and applies equal opposite visual
compensation:

- node `3` static Y: `330 -> 322`
- node `3_0` static Y: `8 -> 16`
- node `3_1` static Y: `0 -> 8`
- both `3_0` animation blocks, both active Y keys: `3 -> 11`

Transform proof:

- text anchor world Y: `330 -> 322`
- panel static world Y: `338 -> 338`
- panel animated world Y: `333 -> 333`
- auxiliary visual world Y: `330 -> 330`

V19's `[1, 1]` special-root block is retained. No message, FIM, font,
texture, or `cockpit2P.arc` resource is modified.

## Artifacts and validation

- live mirrored `cockpit1P.arc` SHA-256:
  `d57c2929b52e574dc8bda16f168e4b28ea2edcd2965fbd45569d2dde856fbd98`
- root-ready ZIP:
  `Utage_Battle_Dialogue_V20_TEXT_BASELINE_COMPENSATION_ROOT_READY.zip`
- ZIP SHA-256:
  `f6bab74bbf66abbbad93e95523f3aad6d84ca1b5018f741ca407783608363337`
- validation report:
  `V20_TEXT_BASELINE_VALIDATION.json`
- independent auditor:
  `audit_v20_text_baseline.py`
- pre-V20/V19 backup:
  `V20_BACKUP_cockpit1P_pre_v20.zip`

Independent audit passed: only ARC entry 18 differs from V19; exactly 11 raw
LSP bytes changed at the declared seven f32 fields; ENG/JPN outputs are
byte-identical; all untouched compressed resources are preserved; ZIP CRC and
package/live equality pass; `cockpit2P.arc` remains SHA-256
`9ab7fe47ff26eb9960695190838c0edd4e9bf670590adcbbee6e3596cbadd10c`.

## Required runtime check

Fully close RPCS3 and cold boot Utage m034/pl015 without a save state. The
glyph block should move up 12 pixels at 1080p while the panel, portrait, and
speaker-name plate remain at their V19 positions. Check both the same three-line
Masamune exchange and a two-line line, plus the mission banner and other HUD.
