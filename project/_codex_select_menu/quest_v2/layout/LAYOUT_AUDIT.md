# Quest menu native-cell repair

The screenshots match `rom/eng/quest/menu.arc`, LSP entry 44,
`id\lsp\jpn\yuugi_quest\yuugi_quest`. Both installed ENG and JPN LSPs are
byte-identical: SHA-256
`91516511cb56f80b0914f456c616286ee333588b6b959ba336d0b2f0d7d1d6fe`.

The node-name table was parsed as one name and one texture string for **every**
node, with no string alignment padding, then checked against
`build_v18_dialogue_alignment.node_names`. All 302 node mappings agree.

The fundamental failure is the translated images ignoring their native atlas
cells. XET decoded-image coordinates are twice the LSP UV coordinates on both
axes. A before/after crop preview at these exact coordinates is in
`NATIVE_CELL_BEFORE_AFTER.png`. This is an offline sampling preview, not RPCS3.

## Resources ready for integration

- `entry_30_native_cells.xet` replaces menu.arc entry 30,
  `id\texture\jpn\yuugi_quest\yuugi_quest_002_ID_HQ`.
- `entry_38_native_cells.xet` replaces menu.arc entry 38,
  `id\texture\jpn\yuugi_quest\yuugi_quest_001_ID_HQ`.
- `NATIVE_CELL_VALIDATION.json` records source/output hashes, touched cells,
  exact restored BC3 block counts, and untouched-block assertions.
- `repair_native_cells.py` rebuilds these resources from guarded live sources.
  It writes only to this layout working directory. It does not install files.

## Exact ownership and changes

| Symptom | LSP node | Native UV | Physical image rectangle | Repair |
|---|---:|---|---|---|
| Prefix `IRED` before difficulty | 84 Nnd_tx | 108,228,192,252 | 216,456,384,504 | Fit existing DIFFICULTY mask entirely inside cell |
| Gold star is a triangle | 86–90 Star_0..4 | 108,128,132,152 | 216,256,264,304 | Restore 144 native JPN BC3 blocks |
| Star outlines/fill alignment | 85 Nnd_star_u | 0,176,108,200 | 0,352,216,400 | Restore 648 native JPN BC3 blocks |
| Fastest label cuts off | 91 Spd_tx | 0,152,108,176 | 0,304,216,352 | Fit full existing FASTEST CLEAR TIME mask |
| Colored lines around reward bullets | 109/116/123/130/137 Point | 132,128,148,152 | 264,256,296,304 | Restore 96 native JPN BC3 blocks |
| Stray top marks above REWARD | 106 Ghb_tx | 192,220,256,252 | 384,440,512,504 | Clear native cell and fit complete REWARD mask |
| Stray mark after CLEARED WARRIORS | 153 Tasseibusyo | 0,200,164,228 | 0,400,328,456 | Fit existing full words with clean padding |
| `LEN` between count digits | 285 Line | 42,216,66,248 | 84,432,132,496 | Restore 192 native JPN BC3 slash blocks |
| `CHAL` next to count | 297 Yugisu | 0,216,42,248 | 0,432,84,496 | Clear redundant unit cell, leaving selected/total |

Clear time and challenges-cleared labels are also fit to their respective native
cells so their pixels cannot spill into neighboring symbols. Existing English
glyph shapes are reused; no translations or fonts are substituted.

Every XET header, resource length and BC3 block outside the explicit target
rectangles is preserved against the current ENG resource. The star, underlay,
reward bullet and slash are byte-exact original compressed blocks. The LSP is
unchanged, preserving parents, stable IDs, material references and animation
blocks; the numeric counter and runtime difficulty logic are untouched.

## Quest-title advice for the primary builder

List title nodes 6,14,22,30,38,46 use native UV `0,0,180,32`, sampling physical
image `0,0,360,64`. The top-right title node 78 uses `0,32,180,64`, sampling
physical image `0,64,360,128`. Existing title textures are 512x128 and current
English text extends through x~500, which explains exact truncation.

Fit both title-state glyph masks into physical x0..356 (prefer x4..352), centered
within each 64px state row. Use approximately 28px maximum ink height for readable
text of consistent height. Keep full wording and shrink long titles to fit.
This fixes the known crops without depending on whether dynamic Q_name updates
override the LSP's UV/geometry. The first list Q_name is type 3; other copies are
type 2 and all use `id\dummy_BM` until runtime substitutes a quest texture.

## Encoding caution

These resources use GREEN as the shader mask. The ordinary helper encoder
`build_free_battle_v6.patch_bc3_rect` picks the brightest RGB color for pixels
with alpha below 8, creating visible bright rectangular blocks in the green
channel. The local `patch_bc3_rect` in `repair_native_cells.py` encodes alpha and
RGB separately, preserving green=0 even when alpha=0. The corrected green-channel
decode was visually checked. Use this helper for texture fitting or another
encoder that retains RGB at transparent pixels.

RPCS3 cold-boot verification remains required; these outputs establish native
UV correctness and byte scope, not runtime completion.
