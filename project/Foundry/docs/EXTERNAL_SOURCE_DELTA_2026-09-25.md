# External Source Delta — REvilLib / Kuriimu2 / MT Framework Tool — 2026-09-25

Purpose: record only findings that add something materially new to BASARA Foundry, not generic confirmations.

## 1. REvilLib has first-class Sengoku BASARA title profiles

External source:
- PredatorCZ/RevilLib `database/data/sb3.ini`
- PredatorCZ/RevilLib `database/data/sbsh.ini`

Observed:
- `sb3` and `sengoku_basara_3` are explicit title aliases.
- `sbsh` and `sengoku_basara_samurai_heroes` are explicit title aliases.
- Both use TEX version `0x97`.
- Both use LMT version `56`.
- Both expose PS3 class->extension mappings including `rArchive=arc`, `rAscii=asc`, `rLayoutSpr=lsp`, `rMessage=msg`, `rTexture=tex`, and many game-specific classes.

Status: **PROVEN EXTERNALLY**.
Value: REvilLib can be used as an independent Capcom-family taxonomy source for class/extension/version cross-checking instead of relying only on our extracted trees.

Do not treat the database as Utage runtime authority; it is external implementation evidence.

## 2. PS3 ARC support tuple: v8 + zlib window 14 + raw members allowed

External source:
- PredatorCZ/RevilLib `database/make_db.cpp`
- PredatorCZ/RevilLib `toolset/arc_conv/make_arc.cpp`
- PredatorCZ/RevilLib `src/arc.cpp`

Observed:
- REvilLib defines `ARC_PS3_GENERIC{8, 14, true}`.
- This means ARC version 8, zlib window size 14, and `allowRaw=true` in its title-support database.
- Its PS3 writer may store a member raw when compression is not worthwhile.
- Its reader explicitly accepts PS3 members where `compressedSize == uncompressedSize` as raw bytes.

Status: **PROVEN EXTERNALLY; NOT YET PROMOTED TO UTAGE FORMAT CANON**.
Why this matters:
- BASARA Foundry currently documents ARC v8 and preservation rules, but does not document the external window-14/raw-member support tuple.
- This may explain valid raw members and may matter to byte-faithful rebuilds.

Required validation:
1. census fresh Utage ARC members for compressed-size == uncompressed-size cases;
2. inspect zlib CMF/FLG on compressed members and derive actual window declaration;
3. compare current Foundry writer output with the source member's zlib header/window behaviour;
4. only then decide whether window-14 should become a certified Utage writer rule.

## 3. Format 0x2B: independent PS3 RBxG corroboration vs REvilLib naming

External sources:
- wmltogether/MT-Framework-Tool `PS3/tex2png/capcomTool.py`
- PredatorCZ/RevilLib `src/tex.hpp`
- FanTranslatorsInternational/Kuriimu2 `MtTexSupport.cs`

Observed:
- The PS3-specific MT Framework Tool explicitly maps `0x2B -> RBxG`.
- Its decode representation is exactly:
  - `base=(A,A,A,G)`
  - `mask=(R,B,0,255)`
- Reimport reconstructs stored channels as:
  - `stored=(mask.R, base.A, mask.G, base.G)`
- This matches the current BASARA Foundry 0x2B base+mask representation.
- REvilLib names 0x2A `BC3_YUV` and 0x2B `BC3_YUV_PA`, with a comment suggesting premultiplied alpha.
- Kuriimu2 maps both 0x2A and 0x2B to DXT5 and applies the same YCbCr shader class.

Status:
- RBxG/base+mask representation: **STRONGLY CORROBORATED EXTERNALLY**.
- `0x2B = premultiplied-alpha YUV`: **HYPOTHESIS ONLY**; REvilLib naming/comment is not sufficient to override fixture/runtime evidence.

Next discriminating test:
- select real Utage 0x2B textures with nontrivial stored R/B/G/A;
- compare runtime/visual output under:
  A. current RBxG reconstruction;
  B. same YCbCr transform as 0x2A;
  C. YCbCr plus premultiplication/unpremultiplication;
- use final visual/runtime evidence to bound semantics.

## 4. Old PS3 helper packed-dimension formula is not promoted

External source:
- wmltogether/MT-Framework-Tool PS3 helper reconstructs dimensions using packed bits and x4/x2 scaling.

Counter-evidence:
- REvilLib parses 0x97 through `TEXx9D` and reads 13-bit width/height directly.
- Kuriimu2 explicitly maps version 0x97 to PS3.

Conclusion:
The helper formula may reflect that tool's internal interpretation or an older resource variant. It is **not** promoted to current Utage canon without fixture-level byte comparison.

## Priority order

1. Validate ARC window-14/raw-member behaviour against fresh Utage ARC corpus.
2. Perform a real 0x2B three-model semantics test.
3. Import REvilLib SB3/SBSH class-extension taxonomy as an external cross-check table, clearly labelled external.
4. Continue source-delta hunting only after those tests, because these have concrete falsifiable outcomes.
