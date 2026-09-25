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

Status: **EXTERNAL GENERIC CLAIM TESTED AND REJECTED AS AN UTAGE GENERALIZATION.**

Live corpus validation on 2026-09-25:
- ENG: 4,645 ARC v8 archives, 68,325 members, 68,177 zlib members, 148 raw members, 0 unsupported storage cases.
- JPN: 4,076 ARC v8 archives, 61,252 members, 61,112 zlib members, 140 raw members, 0 unsupported storage cases.
- Every compressed member in both corpora uses zlib CMF `0x78`, which declares a 15-bit/32 KiB window.
- Zero valid compressed members have compressed size equal to declared raw size.
- Raw and compressed entries both use packed low flag value `2` in this corpus; the low bits are not a compression discriminator here.

Conclusion:
- `allowRaw=true` is compatible with real Utage.
- REvilLib's generic PS3 `windowSize=14` must **not** be copied into an Utage writer. Actual Utage corpus evidence is window 15.
- The current Foundry Python/.NET default-zlib writers therefore match the observed window declaration better than the external generic PS3 profile.

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


## 5. ARCS / SCRA child-archive serialization cracked

External clue:
- REvilLib's binary detector explicitly recognizes `CompileFourCC("ARCS")` but does not parse it.
- UMVC3 tooling identifies `0x73850D05` as `rArchive`.

Live Utage proof:
- all 117 `rArchive` members per route are raw ARCS/SCRA records;
- binary layout is `magic + u16 version + u16 count + count*(u32 classHash,u32 pathHash)`;
- path hash is the full 32-bit complement CRC32 of the lowercased internal path;
- 507/507 references per route resolve uniquely inside the containing parent;
- 117/117 manifests per route exactly reproduce the ordered table identities of their standalone child ARC;
- shared resources are deduplicated in the parent and may be referenced by multiple child manifests.

This is the clearest structural proof so far for the parent/child archive relationship behind `title_id`, `pl_all`, `quest_id`, and `friend`.

Status: **STRUCTURALLY VERIFIED**.
