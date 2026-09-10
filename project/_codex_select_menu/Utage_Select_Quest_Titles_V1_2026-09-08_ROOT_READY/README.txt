Utage character-select quest titles - 2026-09-08

This update synchronizes all 31 quest-title textures in rom/eng/select/c_common.arc
with the existing English titles in rom/eng/quest/q000_id.arc through q030_id.arc.
Both 512x64 texture states are copied inside each original 512x128 resource.

Only PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc is included.
Merge PS3_GAME into your existing patched game root and overwrite this one file.
Use this as an add-on to your current English installation, not a full-game patch.

All 45 other entries, including the character-select layout, are preserved as
identical compressed bytes. Resource names, texture headers, dimensions, flags,
entry order, and total resource count are unchanged. No dialogue, conquest-map
messages, waza sheets, or other game files are modified by this patch.

Offline validation passed: archive resources, donor equality, layout preservation,
package CRC and SHA-256. RPCS3 cold-boot testing remains required. In Quest mode,
check character select for quests 01 through 31, both selection states, title
alignment, two-player selection, and return/confirm navigation.

Wording is inherited exactly from the existing English quest menu. In particular,
quest 02 remains SWORDSMAN'S DUEL for consistency; its Japanese title is literally
Gentlemen's Duel. This patch does not independently revise the quest translations.

Rollback: BACKUP_select_c_common_PRE_2026-09-08.zip restores the exact previous
c_common.arc. Keep the backup; avoid using it after later edits to this archive.
