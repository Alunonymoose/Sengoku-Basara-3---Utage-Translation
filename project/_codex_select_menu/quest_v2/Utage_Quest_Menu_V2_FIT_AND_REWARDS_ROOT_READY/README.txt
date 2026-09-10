Utage Quest Menu V2 - fit and reward corrections

Install by merging PS3_GAME into your current patched game root, overwriting the
included files. This is an additive menu update, not a full-game translation.

Fixes:
- All 31 quest titles fit the native 360x64 sampled cells, with ink height <=28px.
  Both rows and all copies in quest/qNNN_id, quest/quest_id and select/c_common agree.
- English QUESTS heading and Select a battle location instruction.
- Difficulty and fastest-time labels fit their exact native cells.
- Original filled-star, five-star underlay, reward-marker and slash blocks restored.
- Overlapping counter word removed, retaining selected/total numbers.
- 55 semantically mapped reward-name sheets, 161 archive-local copies, fitted to
  native name rows. The Miyoshi brothers retain Eldest/Middle/Youngest distinctions.
- English Z currency marker.

All LSPs, scripts, messages, portraits, other textures and unrelated compressed
resources are preserved. Claude's dialogue and tenka_msg000/001 files are excluded.
Shader-aware encoding preserves text-mask RGB even in transparent pixels.

Validation: archive/resource identities, untouched bytes, donor/mapping manifests,
texture headers and dimensions, native-cell crops, ZIP CRC and hashes passed.
Runtime is NOT verified: cold boot RPCS3 and check quest03, long titles, star values,
reward names and the 03/31 counter. Also check scrolling, cleared list and returns.

Rollback: sibling BACKUP_PRE_QUEST_MENU_V2.zip restores all34 pre-update archives.
Do not restore this backup over later changes to these same files.

Quest title wording is inherited from the English quest menu, including
SWORDSMAN'S DUEL. This release fixes the reported display defects.
