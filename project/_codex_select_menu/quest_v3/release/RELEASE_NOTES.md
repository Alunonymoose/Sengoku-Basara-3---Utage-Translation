# Utage menu repair V3

This is the focused character-select and Japan's Event menu update. It includes
41 current English archives and retains the earlier V2 quest-title, counter and
star repairs. It is not a complete game or a replacement for the full English patch.

Changes:
- Nine archive-local copies of charasele_00_000 now use the same coloured brush
  lettering: Heroes' Story, Unification, Japan's Event, Versus and Quick Battles.
- Selection diamonds, arrows, locks, CPU markers and number sprites retain the
  original Japanese texture blocks. Player badges, Deploy and Battle are English.
- Quest reward rows use the exact original background blocks. The CLEAR/GET
  stamps are fitted inside their own slots, removing the repeated pink streaks.
- 55 reward-name sheets / 161 copies have stronger ivory lettering and dark
  outlines. Seven especially weak names use newly generated readable lettering.
- The actual official Samurai Heroes Z currency sprite replaces the Japanese unit
  in the affected archives; all digit cells are preserved.

Validation: independent archive reader passed; 179 resources changed, 949 other
compressed resources preserved, all 20 LSP layout resources unchanged. Every name
is bounded to its native 256x48 row. Frame/background/star blocks were checked
against the immutable Japanese source. ZIP CRC and per-archive hashes are checked
before installation. These are offline checks, not a claim of runtime success.

For another installation, merge the included PS3_GAME folder into the existing
patched game root. This package snapshots other resources in these 41 archives;
do not apply it over newer unrelated edits to the same archives without rebasing.

Cold-boot RPCS3, then check character select, Japan's Event quest03, the longest
quest titles, all reward names, cleared/get indicators, stars, scrolling and
1P/2P selection. Do not use a save state carrying the old menu textures.

Claude-owned msg_* dialogue and tenka_msg000/001 were not edited. No Japanese
reference, demo resource, executable or save data was modified.

The rollback archive BACKUP_PRE_V3.zip is beside this package in the workspace.
See ARTWORK_NOTES.md for the built-in ImageGen brief and retained masters.
