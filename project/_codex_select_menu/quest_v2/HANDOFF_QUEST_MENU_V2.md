# Quest Menu V2: installed; runtime confirmation pending

User screenshots showed the actual Quest list (`eng/quest/menu.arc`), not only
character select. They reported oversized/cropped quest titles, Japanese heading
and reward names, corrupted bottom counter and difficulty stars.

V2 is installed into `E:\Utage Patching New`. It changes 34 archives: the 33
`eng/quest/*.arc` files and `eng/select/c_common.arc`. It replaces 259 texture
resources and preserves all 341 other compressed resources, every LSP, internal
resource name, metadata/order, and texture header/dimensions.

## Completed changes

- Fit all 31 English quest-title masks to <=350 pixels wide and <=28 pixels ink
  height within each native 360x64 sample, synchronize all 93 copies.
- English QUESTS mode heading; existing English Select a battle location prompt.
- Repair labels inside native atlas cells, restore exact original star, dot and
  slash blocks, clear the redundant counter word so selected/total remains.
- Semantically remap 55 reward-name sheets across 161 copies. Names are fitted to
  their 256x48 cells. Never use same-number SH donors for Utage-exclusive IDs.
- Replace Japanese currency unit with the existing English Z symbol.

Shader-aware BC3 encoding must retain RGB for alpha-zero pixels. The older generic
encoder does not do that and produces solid-block green-mask artifacts. The new
encoder is in `layout/repair_native_cells.py`. Original English title alpha masks
were used because the older encoding polluted their invisible RGB edges.

No Claude-owned dialogue `eng/id/msg_*_pl*.arc` or conquest messages
`eng/tenka/tenka_msg000.arc` / `tenka_msg001.arc` were modified. No files in the
Tenka directory were written. All Japanese-reference files remain untouched.

## Deliverables

- `Utage_Quest_Menu_V2_FIT_AND_REWARDS_ROOT_READY.zip`
- SHA-256 `fd10d305665dfb2abea497297e87a820e19805ede07a3165eca7781031be68eb`
- `BACKUP_PRE_QUEST_MENU_V2.zip`: exact original 34 archives, CRC/hash verified.
- `RELEASE_VALIDATION.json`: resource manifests and installed hashes.
- `INDEPENDENT_RELEASE_CHECK.json`: independent struct/zlib reader verified all
  resource metadata, payloads, untouched bytes and package integrity.
- `MENU_FIX_PROOF.png`, `titles/TITLE_FIT_PREVIEW_*.png`,
  `layout/NATIVE_CELL_BEFORE_AFTER.png`, `rewards/REWARD_CANDIDATES_*.png`: inspected
  decoded texture proofs. These are NOT runtime screenshots.

## Runtime check still required

Cold-boot RPCS3 and check quest03 and the longest quest names, header, all star
values, reward rows, 03/31 counter, cleared list, scrolling and return navigation.
No runtime success is claimed. V1 and original quest-menu issues are superseded
only by this candidate until the user confirms the new screen.

## Artwork provenance

Built-in ImageGen produced the QUESTS heading mask and the three-row Miyoshi
Eldest/Middle/Youngest lettering atlas. Selected masters are under `heading/`;
QUESTS prompts are in `heading/GENERATION_NOTES.md`. Miyoshi brief: three separate
rows spelling Miyoshi (Eldest), Miyoshi (Middle), Miyoshi (Youngest), white serif
italic lettering on black. The existing generated image was converted to row
coverage masks and resampled mechanically into native cells. All other lettering
was reused from existing English resources; no local-font replacement text was
introduced during this repair.

Quest02 retains existing SWORDSMAN'S DUEL wording. Any future translation change
should be synchronized across its consumers. The Japanese literally means
Gentlemen's Duel. Start future fixes from current live files, not older backups.
