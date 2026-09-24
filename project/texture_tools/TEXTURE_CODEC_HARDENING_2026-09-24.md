# 2026-09-24 RUNTIME HOTFIX SUPERSESSION — TITLE_004 BC ENDPOINT ORDER

The earlier endpoint-endian conclusion in this document is **superseded**.

A current live `title_004_ID_HQ` fixture (SHA-256 `87446f8847e56da3c660637f71709e6cea0bc4e74e204ccd1be8127fbe05a375`) plus an actual game runtime screenshot disproved the synthetic PS3 RGB565 byte-swap bridge. With the byte swap, the title renders a green rectangle with magenta/pink Sengoku artwork. The same live fixture decodes correctly as the known blue/transparent Sengoku artwork when its DXT5/BC3 RGB565 endpoint words are handled in standard BC3 byte order.

Kuriimu2's PS3 path registers `0x2A` as `ImageFormats.Dxt5()` and separately applies `MtTex_YCbCrColorShader`; it does not add an endpoint byte-swap layer. Therefore:

- XET header/table fields remain big-endian.
- Verified `0x2A/title_004` BC3 payload endpoint words use standard DXT5/BC3 byte order.
- The Foundry endpoint-swap bridge is invalid for this verified path and must be removed.
- Normal incremental edits preserve CURRENT LIVE TARGET compressed blocks outside the approved mask; pristine/JPN is not the default payload base.
- A production writer must first reproduce the exact current live fixture semantically. A synthetic self-roundtrip is insufficient evidence.

This supersession is backed by a real live fixture and runtime failure and therefore outranks the synthetic endpoint fixture that motivated the earlier bridge.

---

# BASARA Foundry — Texture Codec Hardening — 2026-09-24

## Status

This note supersedes the older operational claim that the project has no durable current XET writer.

A durable **single-mip, swizzle=0 BC3 write/block-graft path now exists in Foundry** and has passed the current synthetic/core smoke suite after correction to the solved PS3 contract.

This is software/fixture certification, not a blanket runtime certificate for every texture family.

## What was wrong

The older C# `UtageXetCodec` / `UtageBc3BlockGraft` path predated the 2026-09-23 solved PS3 BC contract.

It passed PS3 BC payload bytes directly to BCnEncoder.Net.

**SUPERSEDED:** that conclusion came from a synthetic fixture. The verified current 0x2A/title_004 payload uses standard BC3 endpoint byte order; do not byte-swap RGB565 endpoint words.

The same old API also exposed raw BC-decoded storage channels as if they were always artist-facing RGBA.

That is wrong for format `0x2A`, whose PS3 MT Framework encoding uses the Kuriimu2 YCbCr colour shader.

## Current C# production contract

Canonical files:

- `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetReader.cs`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetCodec.cs`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageBc3BlockGraft.cs`

### PS3 BC endpoint bridge

Before BCnEncoder.Net decode:
- swap each block's RGB565 endpoint 0 bytes;
- swap RGB565 endpoint 1 bytes;
- leave alpha endpoint/index and colour-index byte arrays unchanged.

After BCnEncoder.Net encode:
- perform the inverse endpoint swap before writing PS3 payload bytes.

Supported by independent smoke fixtures rather than only encode→decode self-consistency.

### 0x2A — BC3 storage + YCbCr display/write shader

For artist/game-visible RGBA input `(R,G,B,A)`:

```
Y  = 0.299R + 0.587G + 0.114B
Cb = 123 - 0.168736R - 0.331264G + 0.5B
Cr = 123 + 0.5R - 0.418688G - 0.081312B
stored RGBA = (Cr, A, Cb, Y)
```

For BC-decoded stored channels `(storedR,storedG,storedB,storedA)`:

```
display alpha = storedG
Y  = storedA
Cb = storedB - 123
Cr = storedR - 123
R = clamp(Y + 1.402*Cr)
G = clamp(Y - 0.344136*Cb - 0.714136*Cr)
B = clamp(Y + 1.772*Cb)
```

Therefore:
- preview APIs expose **display RGBA**;
- candidate art is supplied as **display RGBA**;
- the codec performs the shader conversion before BC3 compression;
- final verification decode returns display RGBA.

This does NOT revive the disproven old claim that the XET payload is a bespoke raw YUV structure. The payload is standard block-compressed BC3; the format additionally has a colour shader.

### 0x15 — DXT3 / BC2

Real Utage fixture + historical Kuriimu2 mapping establish:
- format 0x15 = DXT3 / BC2 for read/preview;
- **SUPERSEDED for verified 0x2A/title_004:** no RGB565 endpoint byte-swap bridge; use standard BC3 payload byte order.
- explicit BC2 4-bit alpha is decoded normally.

Production writing remains disabled pending a real current Utage:
candidate → BC2 encode → block graft/rebuild → re-extract/decode → runtime test.

### 0x2B

Generic one-plane RGBA preview/write is blocked.

Project evidence requires the dedicated RBxG/base+mask representation. Do not route 0x2B through ordinary RGBA APIs.

### Still fail-closed

- non-zero swizzle without a certified path;
- multi-mip/trailing-data write;
- BC1 writes until explicitly certified;
- BC2 writes;
- 0x2B writes;
- unknown formats.

## Block-graft rule

For supported BC3:
- candidate equality outside the exact edit mask is checked in **display RGBA**;
- edit mask expands to intersecting 4×4 blocks;
- only those encoded PS3 BC3 blocks are imported;
- untouched compressed blocks remain byte-identical;
- final XET is decoded again;
- no display-pixel delta may exist outside the effective touched-block footprint.

## Current test evidence

Foundry CI run for commit:
`e6ad054e76da33ff666a8436aa56d16b9c42c9b3`

completed **SUCCESS**.

The test set includes independent fixtures proving:
- verified current 0x2A/title_004 standard-BC3 endpoint ordering decodes correctly;
- writer output keeps standard BC3 endpoint byte order for the verified 0x2A/title_004 path;
- 0x2A stored YCbCr channel semantics render expected visible colour;
- visible RGBA is converted to expected stored-channel ranges before compression;
- 0x15 is decoded as DXT3/BC2;
- 0x15 write remains rejected;
- generic 0x2B one-plane RGBA is rejected;
- existing surgical block-graft invariants remain enforced.

Evidence class:
**synthetic/fixture software proof**.

Do not relabel as runtime proof of a newly produced game texture until the exact built ARC is tested.

## Python read/review path

Canonical recovered decoder:

`project/texture_tools/xet_recovery_2026-09-23/foundry_xet_decoder_20260923.py`

Current behavior:
- `decode_storage_rgba()` returns BC-decoded stored channels;
- `decode_rgba()` returns artist/game-visible RGBA;
- 0x2A applies the YCbCr read shader;
- 0x15 decodes as BC2;
- container/header endianness and BC payload endpoint ordering are handled as separate contracts; no inferred endpoint swap is allowed.

Release-audit/visual-review tools must use `decode_rgba()` for human-facing previews.

## Production caution

The title_004 texture remains the strongest existing runtime-verified 0x2A fixture and has artwork-specific transparent-RGB edge conditioning.

That edge-conditioning rule must NOT be generalized automatically to unrelated 0x2A assets.

## Next certification work

1. Run corrected Foundry BC3 production path on a current-live, already-understood 0x2A target and compare the final built decode to an approved candidate.
2. Bind the exact source/output hashes and cold-boot result.
3. Only then promote the corrected current Foundry writer from software/fixture proof to runtime-certified production implementation.
4. Separately certify BC2 writing only if a real 0x15 localisation job requires it.

