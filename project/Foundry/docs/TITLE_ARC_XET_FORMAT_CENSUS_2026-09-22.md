# TITLE.ARC XET FORMAT CENSUS — 2026-09-22

Fixture:
- exact runtime source ARC used by the accepted 2026-09-18 title_004 build
- ARC SHA-256: `201010cc5d4bbee203c5988f5c4827da18e09a91e87c83525debb94047bb75dd`
- 357 ARC members
- 264 XET resources

## Format / mip census

Observed XET tuples (format, swizzle, mipCount):

- 0x17, swizzle 0, mip 1: 73
- 0x17, swizzle 0, mip 2: 2
- 0x17, swizzle 0, mip 3: 4
- 0x17, swizzle 0, mip 4: 4
- 0x17, swizzle 0, mip 5: 6
- 0x17, swizzle 0, mip 6: 8
- 0x19, swizzle 0, mip 1: 24
- 0x19, swizzle 0, mip 3: 1
- 0x27, swizzle 0, mip 3: 1
- 0x27, swizzle 0, mip 5: 2
- 0x27, swizzle 0, mip 6: 1
- 0x2A, swizzle 0, mip 1: 138

No non-zero-swizzle XET occurs in this title fixture.

No format-0x2B XET occurs in this title fixture.

## Localisation/UI family

All 132 XETs under `id\texture\...` are:
- format 0x2A
- swizzle 0
- mipCount 1

There are six additional 0x2A/single-mip title-message textures:
- `msg\id_title\jpn\id_title_00_ID_HQ`
- `msg\id_title\jpn\id_title_01_ID_HQ`
- `msg\id_title\jpn\id_title_02_ID_HQ`
- `msg\id_title\jpn\id_title_03_ID_HQ`
- `msg\id_title\jpn\id_title_04_ID_HQ`
- `msg\id_title\jpn\id_title_05_ID_HQ`

Therefore the title localisation atlas family is overwhelmingly the already-important 0x2A one-mip path.

## Multi-mip census

29 XETs have mipCount > 1.

Every multi-mip XET in this fixture belongs to stage/effect material resources. None is under `id\texture\...`, and none is one of the title localisation/message atlases.

Representative families:
- `effect\tex\...`
- `stage\msel\...`

This means Foundry's current fail-closed multi-mip writer is not a blocker for normal title/UI localisation work in this fixture.

Do not weaken the multi-mip gate. A full mip-chain writer should only be implemented when a real localisation target requires it.

## Priority consequence

For title/UI production:
1. 0x2A display-space decode/write correctness is high priority.
2. Current-live-target BC3 preservation and block-graft correctness is high priority.
3. Real-fixture regression against runtime-accepted title_004 is high priority.
4. Multi-mip writing is lower priority for this family.
5. 0x2B remains an unresolved cross-game/other-family research item; title.arc does not supply a fixture.

This census is fixture-specific and must not be generalized to every ARC in Utage without a broader corpus scan.
