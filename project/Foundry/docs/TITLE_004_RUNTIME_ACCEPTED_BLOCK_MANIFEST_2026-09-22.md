# TITLE_004 RUNTIME-ACCEPTED BLOCK MANIFEST — 2026-09-22

Purpose: non-copyrighted golden regression metadata derived from the exact runtime-accepted 2026-09-18 clean-edge title build. No Capcom payload bytes are stored here.

## Exact runtime fixture

Source ARC SHA-256:
`201010cc5d4bbee203c5988f5c4827da18e09a91e87c83525debb94047bb75dd`

Accepted ARC SHA-256:
`6350620a27ab0dcd43fa695ef305a387bf8a3067be9d6cfa4489231266b11c82`

Source `title_004_ID_HQ` XET SHA-256 extracted from that exact source ARC:
`7a0a18ff0360e6a8f0971047a5524075c271caff494fed4a5019d2186ac687bc`

Accepted `title_004_ID_HQ` XET SHA-256:
`978f00c5709edb4553473ba8b1b3ae6bd760a8517a5fdb34b0371125775a3808`

Important: this exact runtime source XET is an already-modified project baseline. Earlier pristine/diagnostic `title_004` hashes in research notes are different fixtures and must not be substituted when reproducing this accepted transaction.

## XET structure

- dimensions: 512x256
- format: 0x2A
- storage: BC3/DXT5
- texture offset: 0x14
- blocks: 128x64 = 8192 total
- XET header/shell before payload: byte-identical source -> accepted

## Runtime-accepted changed-block footprint

Fixture-proven `logo_sengoku` physical source rectangle:
- x = 0..367
- y = 0..175
- BC3 block rectangle = bx 0..91, by 0..43
- rectangle contains 4048 BC3 blocks

Exact source -> accepted diff:
- changed BC3 blocks: **4046**
- unchanged BC3 blocks inside the 368x176 rectangle: exactly **2**
  - block (70,14)
  - block (33,19)
- all **4144** blocks outside the 368x176 rectangle are byte-identical
- total unchanged blocks across the XET: **4146**
- no changed block exists outside the fixture-proven logo rectangle

Therefore the accepted transaction's block footprint is equivalent to:
`all blocks in bx 0..91/by 0..43 except (70,14) and (33,19)`

The two in-rectangle unchanged blocks are not special exclusions from the intended mask; their final compressed bytes simply remained identical to source.

## ARC preservation proof

The source and accepted title ARCs each contain 357 members.

Stored-member comparison proves:
- exactly **1/357** stored ARC member payloads changed: member 294, `id\texture\jpn\title\title_004_ID_HQ`
- the other **356/357** stored member payloads are byte-identical
- `title_005_ID_HQ` remains byte-identical
- `title_006_ID_HQ` remains byte-identical

This is the golden preservation invariant for the accepted build.

## Regression use

A future 0x2A implementation should be able to consume the exact external fixture when supplied by the operator and assert:
1. source ARC/XET hashes match this manifest;
2. output XET shell/header is preserved;
3. no changed BC3 block lies outside bx 0..91/by 0..43;
4. all ARC members except member 294 remain stored-byte-identical;
5. final built XET is decoded in 0x2A display space before approval;
6. runtime certification remains separate unless the produced binary is already the accepted XET hash above.

Do not check the proprietary ARC/XET bytes into GitHub. Keep only hashes, geometry, counts, and derived block coordinates/constraints in the repository.
