# Character-select quest titles, 2026-09-08

Installed a quest-title-only pass into the live `E:\Utage Patching New` game.

- Sole changed game archive: `PS3_GAME/USRDIR/nativePS3/rom/eng/select/c_common.arc`.
- Replaced entries 31 through 61 (`quest_000_ID_HQ` through `quest_030_ID_HQ`) with existing English textures from `eng/quest/q000_id.arc` through `q030_id.arc`. These donors also match `eng/quest/quest_id.arc`.
- Kept each resource's original 20-byte XET header, 512x128 BC3 dimensions, internal JPN name, type, flags, and archive order. Both 64-pixel texture states were retained.
- The other 45 resources, including LSP entry 75, retain exact compressed bytes.
- No game files outside this one archive were written. In particular, Claude's active `eng/id/msg_*_pl*.arc` dialogue and `eng/tenka/tenka_msg000.arc` / `tenka_msg001.arc` were not edited.

Source archive SHA-256: `fc0a08a9b50b07662774616f457795670ecd9b7ba11e54bfcddd4082a5e71f2f`.

Installed archive SHA-256: `3bf1fc66083333f1cf0948a7005070fd8ba2ae26888c325a30ae7c6c98de7817`.

Package: `Utage_Select_Quest_Titles_V1_2026-09-08_ROOT_READY.zip`.

Package SHA-256: `17d24590dfa7f91cbb4c5763a12a1d31a725d247f27f80f28c906173e74dd6ec`.

Rollback: `BACKUP_select_c_common_PRE_2026-09-08.zip`.

## Verification

Builder and independent audit passed archive/donor equality, entry preservation, XET header/shape, ZIP CRC, payload hashes and package SHA checks. Installed file was read back and matched the validated payload. The native `dummy_BM` resource's pre-existing declared/actual-size convention (1432/1044) was preserved exactly.

RPCS3 was not running and no runtime test was performed. A fresh boot must check Quest-mode character select, long titles, both visual states, two-player selection, and confirm/back navigation before promoting this candidate as runtime-proven.

## Scope and continuation

This is a quest-title pass, not completion of every select texture. Other Japanese menu art and `waza2_001..029` remain unchanged. The separate Japanese copies in `eng/tenka/quest_q000..030.arc` also remain unchanged and should be coordinated with the conquest work before any follow-up.

Wording matches the existing English quest menu without new font rendering. Quest 02 inherits `SWORDSMAN'S DUEL`; the Japanese literally means Gentlemen's Duel. Any correction should synchronize all consumers, not rename select alone. Full title ledger: `translations/QUEST_TITLE_REVIEW.md`.

User's cross-worker terminology: Samurai Heroes spellings `Saica`, `Kanbe`, `Mori`; お館様 is `Lord Shingen`.

Future select work must branch from the installed hash above or the then-current live file. Do not reinstall the pre-pass archive or an earlier cumulative package over newer select edits.
