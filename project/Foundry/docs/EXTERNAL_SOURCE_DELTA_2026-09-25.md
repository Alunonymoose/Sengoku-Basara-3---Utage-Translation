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


## 6. Whole-game texture census removes 0x2B from Utage scope

A live route-wide census inspected 97,800 rTexture/XET entries across current ENG and JPN ARCs.

Observed formats are only 0x2A, 0x17, 0x15, 0x19 and 0x27. Format 0x2B appears **zero times** in both routes.

Conclusion:
- the PS3 RBxG implementation is useful cross-game corroboration;
- REvilLib's 0x2B naming remains interesting generic MT Framework evidence;
- neither should consume Utage production effort unless a real Utage 0x2B fixture is discovered.

Status: **STRUCTURALLY VERIFIED for the scanned current routes**.


## 7. Utage's complete live class universe matches SB3 taxonomy

The current JPN route contains 48 unique ARC type hashes. Every one resolves against REvilLib's `sb3.ini` PS3 resource-class map.

- 48/48 resolved by SB3.
- 39/48 also resolved by Samurai Heroes.
- 9/48 are SB3-profile classes absent from REvilLib's Samurai Heroes profile.
- 0 live Utage hashes require a Samurai Heroes-only class.
- 0 remain unknown after SB3 cross-resolution.

This gives BASARA Foundry an external name/extension authority for the complete observed Utage resource-class set, while live bytes remain the production authority.


## 5. ARC member size word is a 29+3 bit field

Cross-source agreement:
- REvilLib: `ARCFileSize` defines 29 size bits + 3 flag bits and defaults flags to 2.
- Kuriimu2: big-endian `GetDecompressedSize = DecompSize >> 3`; writer preserves `DecompSize & 7` and stores `size << 3`.
- MT-Framework-Tool PS3 repacker: reads `sizetmp >> 3`; writes `(len(zdata) << 3) | 0x2`.

Status: **STRONGLY CORROBORATED STRUCTURAL FACT**.

The individual flag-bit meanings remain unresolved. Preserve the low 3 bits on live entries.

## 6. Proven Kuriimu PS3 BC transform is 4x4 Morton colour ordering

Historical Kuriimu2 revision `6babcdc3562975f445f258f0b7f1d9bd8e5e2a83` applies `BcSwizzle` to PS3 block-compressed textures.

`BcSwizzle` uses bit coordinates `[(1,0),(2,0),(0,1),(0,2)]`, creating a 4x4 Morton/Z-order microtile over the colour stream consumed by the BC encoder/decoder.

Status: **PROVEN SOURCE BEHAVIOUR** for that revision.

Impact: supersedes the project's old vague 8x4-BC-block swizzle rule. Do not generalize beyond the proven transform without fixture evidence.

## 7. Kuriimu source revision must be pinned

The current Kuriimu2 master inspected on 2026-09-25 differs materially from the older proven revision. Its current PS3 loader begins mip iteration at `m=1` and then constructs the image from `mipData[0]`, which is inconsistent for a one-mip texture and differs from the proven revision's `m=0` loop.

Status: **SOURCE-CODE OBSERVATION**.

Impact: do not replace the project's proven Kuriimu path merely because upstream master is newer.


## 8. Live Utage disproves 14-bit zlib-window promotion

A complete live ENG ARC census inspected all 68,325 members.

Results:
- 68,177 compressed members;
- every compressed member is valid zlib;
- only `78 9C` and `78 DA` headers occur;
- both declare `CINFO=7` / 32 KiB window;
- 148 equal-size members are raw and none are zlib.

A direct decompression probe also showed `wbits=15` succeeds while `wbits=14` rejects these streams as an invalid window size.

Conclusion: REvilLib's generic PS3 `windowSize=14` setting is not an Utage live-file property and must not be used as an Utage writer requirement.

## 9. SCRA / rArchive child manifests discovered in live Utage

Live `rArchive` members (`0x73850D05`) reveal an unhandled `SCRA` manifest structure.

117/117 manifests exactly reproduce referenced child ARC membership using pairs of:
- MT resource-class hash;
- full complemented CRC32 of lowercase internal resource path.

All 507 manifested identities are present in their parent resident pools.

This structure is not currently parsed by the public MT Framework tools inspected in this research pass.


## 8. Live Utage SCRA manifests prove parent-child ARC membership

Live E: validation discovered 117 raw `rArchive` members containing `SCRA` records.

Format observed:
- magic `SCRA`
- big-endian version `8`
- big-endian child-member count
- repeated `(resource-class hash, lowercase-path hash)` pairs

The path hash is `(~CRC32(lowercase_internal_path)) & 0xFFFFFFFF`.

Validation result: 117/117 SCRA records exactly matched their referenced child ARC member lists in count, order, class hash and path hash.

Hosts:
- `title_id.arc`: 31 `pl_face` child manifests
- `quest_id.arc`: 31 quest child manifests
- `tenka/friend.arc`: 55 friend/pause child manifests

Status: **STRUCTURALLY PROVEN ON LIVE UTAGE**.

## 9. Parent containers duplicate all manifested child resources, but live payloads can diverge

Across the 117 manifests there were 507 child-resource pairs.

All 507 corresponding resources were present in the parent containers.

Payload comparison:
- 422 exact decompressed-payload matches
- 85 divergences
- all 85 divergences were `rTexture`
- 66 were `id\texture\jpn\cp_name_pl`
- 19 were `id\texture\jpn\cp_name_nak`

Breakdown:
- `title_id.arc`: 123/123 payload-identical
- `quest_id.arc`: 244 identical, 30 divergent
- `tenka/friend.arc`: 55 identical, 55 divergent

Status: **STRUCTURALLY PROVEN ON CURRENT LIVE BUILD**.

Implication: SCRA proves parent-child membership identity, but not byte identity. Parent and child copies can drift independently, so synchronization policy must remain evidence-driven.

## 10. Live ENG ARC corpus resolves all type hashes

Current live ENG tree contains 48 distinct ARC resource-class hashes. Every one resolves against the combined REvilLib SB3/Samurai Heroes class lists using:

`(~CRC32(class_name)) & 0x7FFFFFFF`

No unknown type hashes remain in this live corpus under that combined taxonomy.

Notable correction:
- `0x619CF7E7 = rPalette`
- `0x5E0EF076 = rAscii`

The tiny raw `msg\ascii\...\ascii_*_ID_HQ` resources observed in `basara.arc` / `startup.arc` are therefore typed as `rPalette`, not `rAscii`.

## 11. REvilLib window-size 14 does not describe observed Utage zlib headers

A live sample of 12,427 compressed ARC members yielded only:
- `0x789C`
- `0x78DA`

Both encode `CINFO=7`, i.e. a 32 KiB zlib window.

Sampled members decompressed with `wbits=15`; `wbits=14` returned "invalid window size".

Status: **LIVE UTAGE EVIDENCE CONTRADICTS THE SIMPLE INTERPRETATION** of REvilLib's `windowSize=14` title-profile field.

Do not promote `windowSize=14` as an Utage ARC stream requirement.
