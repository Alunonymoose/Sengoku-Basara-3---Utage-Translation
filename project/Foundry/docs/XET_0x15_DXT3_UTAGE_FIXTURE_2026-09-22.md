# XET 0x15 / DXT3 — REAL UTAGE FIXTURE — 2026-09-22

## Status

XET format `0x15` is source-verified as DXT3 / BC2 for read/preview.

Production writing remains FAIL-CLOSED until a real Utage edit/rebuild/extract/runtime test certifies that path.

## Upstream format evidence

Current Kuriimu2 Capcom MT Framework source (`MtTexSupport.cs`) maps:
- `0x15 -> ImageFormats.Dxt3()`
- `0x17 -> ImageFormats.Dxt5()`
- `0x18 -> ImageFormats.Dxt5()`

This supersedes the earlier project uncertainty that treated 0x15 as BC2/BC3 ambiguous.

## Real Utage fixture

Current sampled `result_id.arc`:
- ARC member index: 60
- logical resource: `id\texture\jpn\wep\wep_000_ID_HQ`
- XET version: 0x97
- dimensions: 512x512
- format code: 0x15
- swizzle: 0
- alphaFlags: 2
- mipCount: 1
- imageCount: 1
- textureOffset: 0x14
- XET size: 262,164 bytes
- image payload: 262,144 bytes

For 512x512, 128x128 blocks × 16 bytes/block = 262,144 bytes, matching the fixture exactly.

A diagnostic BC2 decode is visually coherent and agrees with Kuriimu2's explicit 0x15/DXT3 table.

## Foundry rule

Safe now:
- parse 0x15 metadata;
- decode/preview 0x15 as DXT3 / BC2;
- inspect/reference the texture.

Still blocked:
- direct 0x15 re-encode;
- production block-graft writes;
- any claim that the Foundry 0x15 encoder is runtime-certified.

The write gate must remain closed until a minimal real fixture edit has:
1. known owning ARC and runtime surface;
2. exact candidate/mask review;
3. BC2-aware encode;
4. target-shell-preserving graft;
5. rebuilt-ARC extraction and final decode;
6. runtime verification.
