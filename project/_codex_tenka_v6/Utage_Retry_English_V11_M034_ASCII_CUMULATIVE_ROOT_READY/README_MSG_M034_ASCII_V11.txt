Sengoku BASARA 3 Utage English Patch - m034/pl015 ASCII Repair V11

V11 is cumulative over V10. Merge the included PS3_GAME folder into the
extracted Utage game root and overwrite. Do not reinstall V9 or V10 after V11.

This repair targets the battle dialogue shown as uppercase, wide-spaced text:
  This castle belongs to the Chief of Oshu...

The previous translated archive embedded one uppercase alphabet in Utage's
per-mission Japanese glyph atlas, so uppercase and lowercase source letters
resolved to the same uppercase glyphs. Earlier V9/V10 attempts also duplicated
or wholesale-replaced the text resources. V11 installs one unambiguous route:
the exact retail Samurai Heroes GSM/FIM text payloads under Utage's internal
JPN keys, with Utage's stage script and name textures preserved. The local TNF,
CSA, and mission atlas are absent, forcing the official proportional ASCII font.
Both ENG and JPN global basara font archives are included and synchronized.

Runtime check: cold boot the game, load m034 as player 015, and confirm the line
is mixed case, proportionally spaced, and contained inside the message box.
