# Utage handover addendum — V19 battle-dialogue text origin

Date: 2026-08-31

## Runtime evidence that changed the diagnosis

The user supplied two official Samurai Heroes frames after testing V18. They
show that the character-dialogue plate is fixed-height in the compared two-line
cases. V18 already places the plate, portrait, and speaker-name plate correctly;
the remaining defect is only that Utage's entire glyph block is about 12-14
1920x1080 output pixels too low.

The supplied current `RPCS3.log` is the Samurai Heroes run, not the preceding
Utage run:

- title: `Sengoku BASARA: Samurai Heroes`
- serial: `MRTC00005`
- game root: `E:/SAMURAI HEROES/PS3_GAME`
- loaded archive: `nativePS3/rom/eng/id/cockpit1P.arc`
- no relevant fatal/crash line was found

## V19 diagnosis

No FIM, font, texture, or ordinary node-coordinate patch is warranted:

- installed V18 dialogue group geometry is exact to official SH for the copied
  position/geometry/UV fields;
- the relevant stable-node animation blocks are exact SH:
  - ID 182 `Mess1`: 3 blocks
  - ID 72 `3_0`: 2 blocks
  - ID 77 first `Line_U`: 3 blocks
  - ID 76 `3_1`: 2 blocks
- V15's mission FIM is official SH, including the per-message line count;
- the TNF, CSA, and two active ASCII atlas pages are byte-exact to SH.

The first 208-byte 1P animation block contains two 104-byte special-root tracks
targeting ID `0xFFFFFFFF`. V18/Utage had both tracks disabled (`[0, 0]`), while
official SH 1P uses `[1, 1]`. Utage 2P and SH 2P already agree on their separate
layout-specific pair `[1, 0]`. These are control values, not coordinates.

## V19 edit

V19 changes only the two 1P big-endian u32 enable values from `0` to `1`:

- LSP raw byte offsets changed versus V18: `42435`, `42539`
- LSP size remains `91,480` bytes
- only ARC entry `18` (`id\lsp\jpn\cockpit\cockpit`) differs
- all other compressed ARC resources are byte-preserved
- `cockpit2P.arc` is untouched
- ENG and JPN `cockpit1P.arc` outputs are byte-identical
- installed special-root block is now byte-exact to official SH

## Installed and packaged artifacts

- live mirrored `cockpit1P.arc` SHA-256:
  `6e02355a956d5a645edc908fbc2d5c0c461dd65caed8e9ab05b9e6d996c262c9`
- live LSP SHA-256:
  `aadd36fbf00348b372538b86bf649ccf2e0cca85dffd583e97ecb69e87d6c097`
- unchanged ENG `cockpit2P.arc` SHA-256:
  `9ab7fe47ff26eb9960695190838c0edd4e9bf670590adcbbee6e3596cbadd10c`
- root-ready ZIP:
  `Utage_Battle_Dialogue_V19_TEXT_ORIGIN_ROOT_READY.zip`
- ZIP SHA-256:
  `683a1d888414623eaf49e93e3c07731472b2b9301bba60eda9f88de7c1c1e57b`
- validation report:
  `V19_TEXT_ORIGIN_VALIDATION.json`
- independent auditor:
  `audit_v19_text_origin.py`
- preserved pre-V19/V18 runtime backup:
  `V19_BACKUP_cockpit1P_pre_v19.zip`

The independent post-install audit passed ZIP CRC, package/live equality,
mirrored ENG/JPN hashes, ARC entry identity/count, LSP size, exact two-byte
scope versus V18, exact SH special-root block, and untouched resource
preservation.

## Required runtime check

Offline validation cannot prove the visual effect. Fully close RPCS3 and cold
boot Utage m034/pl015 without a save state. Compare the same two-line Katakura
and three-line Masamune exchanges:

1. the plate, portrait, and speaker name must remain at their V18 positions;
2. the complete glyph block should move upward to the official SH baseline;
3. two-line and three-line centering should remain dynamic from the SH FIM line
   count;
4. verify mission banner, health/Basara meters, partner HUD, minimap, and KOs.
