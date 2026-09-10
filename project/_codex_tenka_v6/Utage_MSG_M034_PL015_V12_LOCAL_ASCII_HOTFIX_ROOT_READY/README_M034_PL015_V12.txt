Sengoku BASARA 3 Utage - m034/pl015 Local ASCII Hotfix V12

Install: merge the included PS3_GAME folder into the extracted Utage game
root and overwrite the single target archive. Cold boot RPCS3 after install.

Target:
  PS3_GAME/USRDIR/nativePS3/rom/eng/id/msg_m034_pl015.arc

V11 removed Utage's local mission font resources and caused this dialogue
set not to load. V12 retains the complete 24-entry Utage archive, restores
the original Japanese TNF/page 14, appends two official Samurai Heroes
proportional ASCII pages, and redirects only GSM records 500 and 501.
The output contains 26 entries. FIM, CSA, all other atlases, the stage
script, and the Utage-specific name textures are preserved.

Runtime check:
  1. Cold boot the game.
  2. Select Oda Nobunaga and Mount Osore.
  3. Confirm the opening dialogue box loads.
  4. Confirm upper/lowercase are distinct and spacing is proportional.

This package has passed offline ARC, resource-scope, SHA-256, and ZIP CRC
checks. The in-engine result still requires the runtime check above.
