# Texture Pipeline Recovery — 2026-09-30

Recovered from the current GitHub Foundry branch plus Drive canon.

## Canonical production rule

XET container fields are big-endian, but BC colour endpoint words use standard DXT byte order. Do **not** byte-swap RGB565 endpoints.

For Utage format 0x2A:
- storage = BC3 / DXT5
- display transform = Kuriimu2 PS3 YCbCr
- stored RGBA = `(Cr, inputAlpha, Cb, Y)`
- neutral chroma = 123
- artist-facing operations occur in display RGBA

Legacy descriptions claiming big-endian BC colour endpoints are superseded.

## Preserved source locations in this branch

- `project/texture_tools/xet_ps3_2026-09-25/`
  - `xet_ps3.py`
  - `xet3.py`
  - `xetenc.py`
  - README
- `project/texture_tools/xet_recovery_2026-09-23/`
- `project/texture_tools/TEXTURE_CODEC_HARDENING_2026-09-24.md`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Arc/UtageSingleEntryXetGraft.cs`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Arc/UtageSharedOwnerXetGraft.cs`
- `project/tools/chat_texture_handoff.py`
- `project/tools/CHAT_TEXTURE_HANDOFF.md`
- `project/Alrummi3/bcn.py`
- `project/Alrummi3/_bcn_validate.py`
- `project/Alrummi3/asset_gen.py`
- `project/Alrummi3/texture_fx.py`

## Production workflow

1. Re-hash exact live ARC.
2. Parse/list member and confirm XET format/mips/swizzle.
3. Decode to display PNG using certified display semantics.
4. Author candidate on a copy of current display output.
5. Approval gate.
6. Re-encode only changed 4x4 BC blocks where possible.
7. Preserve untouched member metadata and untouched payload bytes.
8. Rebuild with certified ARC writer.
9. Re-extract and re-decode the installed candidate.
10. Backup -> install -> readback -> hash -> reparse -> runtime test.

## Important failure history

A self-consistent writer+decoder can both be wrong. The endpoint-order error survived because identity/roundtrip tests did not exercise the game shader correctly. Runtime/display-space checks are mandatory.

## Drive canon provenance

Google Drive document:
`00 TEXTURE PIPELINE CANON — STANDARD BC ORDER + 0x2A YCbCr — 2026-09-25 — READ FIRST (SUPERSEDES XET ENDIAN RULE)`

Drive document id:
`1hHIRJKhKRfmfNIbiK10R4x4qtVToYqm5Qkz1f8RyyCM`

That document states the current production write path and supersessions. This recovery note preserves the operational essentials in GitHub so the project is not dependent on Drive access.
