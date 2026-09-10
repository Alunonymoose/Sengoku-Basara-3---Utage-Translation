Sengoku BASARA 3 Utage - Battle Dialogue V18 Vertical Alignment

V18 corrects the vertical orientation of the in-battle character dialogue
window while preserving the repaired V15 message/font system and the cumulative
Utage cockpit HUD.

Diagnosis: V16 installed Samurai Heroes' Western panel geometry, but its two
dialogue-root animation blocks still used Utage's Y=-2 keys. V17 then selected
animation data by a drifting ordinal name map and replaced unrelated HUD tracks.
V18 starts from the clean pre-V17 V16 backup and changes only four 32-bit Y
values on stable node 3_0 from -2.0 to Samurai Heroes' 3.0. The three long-box
Mess1 tracks, three Line_U tracks, and two 3_1 text-container tracks are proven
byte-identical to official Samurai Heroes and are left untouched.

Merge PS3_GAME into the Utage game root and overwrite. Fully close RPCS3 first,
then cold boot m034/pl015 without a save state. Confirm the Katakura line shown
in the reference screenshot is vertically centered, then trigger a three-line
line to verify the expanded panel, name plate, portrait, health/Basara meters,
partner HUD, KOs counter, and mission banner.
