# Select quest-name audit

Read-only audit completed 2026-09-08. No live game archives changed.

## Immediate patch opportunity

`eng/select/c_common.arc` contains 76 resources. Quest-name textures are entries 31–61, `id\texture\jpn\quest\quest_000_ID_HQ` through `quest_030_ID_HQ`. All are 512×128 XET, format 0x2A/BC3, 65,556 bytes, with a 20-byte header and 65,536-byte pixel payload. Replacing these 31 resources permits preserving the other 45 compressed resources exactly.

The official Samurai Heroes `eng/select` folder is absent, no select files exist inside `SH_ROM_ENG_ARCS.zip`, and the full existing SH resource map contains no matching quest-name textures. However, the live Utage tree already includes translated English copies in `eng/quest/q000_id.arc` through `q030_id.arc`, each at entry 0. Each has an identical copy in `eng/quest/quest_id.arc`. All 31 English donor headers and geometries exactly match their original select copies.

Each quest title has exactly four copies in the scanned live English tree and exactly two raw hashes:

- English: `eng/quest/qNNN_id.arc` and `eng/quest/quest_id.arc`.
- Original Japanese: `eng/select/c_common.arc` and `eng/tenka/quest_qNNN.arc`.

The precise source/donor mapping and hashes are in `EXISTING_QUEST_ENGLISH_DONORS.json`. All 31 English names were visually reviewed in `EXISTING_QUEST_ENGLISH_1.png` through `EXISTING_QUEST_ENGLISH_3.png`. These previews show the green channel because this texture uses channel-packed shader data rather than ordinary RGBA artwork.

## Layout and preservation

`c_common.arc` entry 75, `charasele_hanyo`, contains 413 LSP nodes. Node 403 is `Questname`; it binds `id\dummy_BM`, material 12, geometry and UV `(0,0,256,32)`, size fields `(32,256)`, and scale `(0.9,0.95)`. The game substitutes the actual quest texture dynamically. These placeholder fields alone do not establish the runtime crop. The actual atlas has repeated labels in its top and bottom 64-pixel rows; preserve both rows and the full header/geometry for a donor transplant.

The old `lsp_named_probe.py` parser fails here because it aligns strings and conditionally expects the texture string. This resource instead uses packed, unaligned pairs of node-name and texture strings for every node, including empty texture strings. `build_v18_dialogue_alignment.node_names` implements the correct naming walk; the local audit uses the same interpretation.

No quest-name textures are directly named by static LSP texture references in the scanned tree. `eng/tenka/tenka_finish_id.arc` has dynamic node `Quest` at index 58 with dummy texture, UV `(24,0,232,128)`, geometry `(-104,-64,104,64)` and scale `(0.6,0.6)`. Other quest-related LSPs are in `eng/brief/mode_quest.arc`, its `og` copy, and `eng/quest/menu.arc`, and reference separate `yuugi_quest` art rather than these 31 name textures.

The current ENG and JPN `c_common.arc` are already different, as are ENG/JPN `c_story.arc`; the remaining 10 select archives are byte-identical between language folders. Do not replace JPN whole archives blindly with ENG or assume whole-folder equivalence.

## Audit coverage

Dependency scan: 2,666 ARC headers, 28,582 resource records, and 96 LSP payloads, excluding 1,976 files matching `msg_*_pl*.arc` or named `tenka_msg000.arc`/`tenka_msg001.arc`. No scan errors. Relevant findings are in `QUEST_DEPENDENCY_AUDIT.json`.

The broader SH donor audit is in `SELECT_RESOURCE_DONOR_AUDIT.json`. Future safe opportunities include `c_story.arc` character nameplates: 29 of 30 have unique matching-geometry SH payloads. `cp_name_pl_013_ID_HQ` has a geometry mismatch and must be preserved/rebuilt carefully. The `vs_face.arc` odd-index character labels `charasele_04_000_ID_HQ` through `_029` also have matching-geometry donors in SH `eng/gallery/ranking.arc`; these need visual semantics review before transplant. Common atlas basenames can have multiple donor payloads and are not safe for blind substitution.

Runtime validation remains required after any select patch, especially the quest name during character selection and both row states. This audit establishes resource compatibility and copy relationships, not actual game rendering.
