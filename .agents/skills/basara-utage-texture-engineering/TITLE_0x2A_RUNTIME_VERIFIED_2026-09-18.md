# TITLE 0x2A RUNTIME-VERIFIED CLOSURE — 2026-09-18

This file is a durable engineering checkpoint for the Sengoku BASARA 3 Utage title-logo texture path.

## Evidence status

`title_004_ID_HQ` Sengoku repair: **runtime visually verified and explicitly user approved** for the exact build hashes below. The user supplied the success screenshot immediately after testing the delivered clean-edge build. Cold-boot status was not separately stated in text; preserve that distinction in future evidence summaries.

## Accepted exact build

- Source ARC SHA-256: `201010cc5d4bbee203c5988f5c4827da18e09a91e87c83525debb94047bb75dd`
- Final `title_004_ID_HQ` SHA-256: `978f00c5709edb4553473ba8b1b3ae6bd760a8517a5fdb34b0371125775a3808`
- Final ARC SHA-256: `6350620a27ab0dcd43fa695ef305a387bf8a3067be9d6cfa4489231266b11c82`
- ROOT-READY ZIP SHA-256: `fa4e3eb325a0c1bce75af22d8c8ed2e2738569870ea8aa53dd8648654727eb1c`
- Runtime screenshot SHA-256: `c6ec8240e9f3990f4e996e823f270e94a24803a6a1e71b26eb147ff177b33289`

Canonical binary/evidence backup is in Google Drive:

`BASARA Foundry/04 Runtime Evidence/TITLE_004_RUNTIME_VERIFIED_2026-09-18`

## Verified fixture

- XET version: `0x97`
- format: `0x2A`
- dimensions: `512x256`
- storage: BC3/DXT5
- mip count: 1
- swizzle: 0
- texture offset: `0x14`
- `logo_sengoku` source rect: 184x88 logical = 368x176 HQ physical pixels

## Exact Kuriimu2 0x2A transform

Stored channel meaning:

- `G` = rendered alpha / coverage
- `A` = Y luminance
- `R` = Cr + neutral offset
- `B` = Cb + neutral offset
- neutral chroma center used by this plugin = 123

Write from normal RGBA:

```text
Y  = 0.299R + 0.587G + 0.114B
Cb = 123 - 0.168736R - 0.331264G + 0.5B
Cr = 123 + 0.5R - 0.418688G - 0.081312B
stored = (Cr, inputAlpha, Cb, Y)
```

Read:

```text
alpha = storedG
Y  = storedA
Cb = storedB - 123
Cr = storedR - 123
R = clamp(Y + 1.402*Cr)
G = clamp(Y - 0.344136*Cb - 0.714136*Cr)
B = clamp(Y + 1.772*Cb)
```

## Runtime-verified clean-edge recipe

The successful title build did **not** globally neutralize chroma. It preserved the approved blue logo and grayscale antialiased coverage while preventing black transparent RGB from poisoning BC3 edge colour interpolation.

1. Start from the exact current/live target ARC and freeze hashes.
2. Preserve current target XET shell/header.
3. Preserve approved visible Sengoku art and its full grayscale antialiased alpha.
4. Fill RGB beneath alpha-zero pixels with representative Sengoku blue before the Kuriimu2 0x2A Write transform.
5. Convert through the exact equations above.
6. BC3 encode deterministically.
7. Graft only certified 4x4 blocks inside the 368x176 `logo_sengoku` source rectangle.
8. Preserve every block outside that rectangle byte-for-byte from the live target.
9. Leave `title_005` and `title_006` untouched in a Sengoku-only repair.
10. Rebuild ARC while preserving every unrelated member stored-byte-identical.
11. Re-extract and decode the actual built XET before runtime testing.

## Historical failure guards

Do not:

- write conventional RGBA directly into 0x2A;
- globally force R/B to 123 (runtime v6 produced gray/black Sengoku);
- assume the material supplies all blue tint;
- use black RGB under transparent pixels for this title logo;
- binary-threshold the alpha mask;
- full-sheet production re-encode unrelated blocks;
- modify `title_005` or `title_006` without fresh ownership/effect evidence;
- attribute the old v5 crash to swizzle without proof;
- use the quarantined INVALID 2026-09-18 XET/ARC helpers.

## Scope

The YCbCr channel contract is runtime validated on this real 0x2A fixture. The transparent-RGB prefill is a proven solution for this specific title-logo artwork/fixture. Other 0x2A assets should use the same channel transform but still compare their own pristine edge/material behavior before adopting the exact same art-preconditioning rule.
