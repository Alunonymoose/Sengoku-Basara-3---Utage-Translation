Sengoku BASARA 3 Utage - Battle Dialogue V19 Text Origin

V19 corrects the final vertical text-origin mismatch seen after V18. Official
Samurai Heroes screenshots confirm the dialogue panel is a fixed-height plate;
the Utage V18 panel, portrait, and name plate are already correctly positioned,
but the rendered glyph block sits about 12-14 output pixels too low.

V18's panel geometry, relevant child animations, Samurai Heroes FIM metrics,
ASCII TNF/CSA, and atlas pages are already exact. The remaining 1P difference
is two disabled special-root animation records targeting ID FFFFFFFF. Official
SH enables both in 1P; Utage's 2P layout already matches SH on its [1, 0]
pair. V19 changes only the two 1P big-endian u32 values from 0 to 1. It does not alter coordinates,
textures, messages, fonts, FIM records, or cockpit2P.arc.

Merge PS3_GAME into the Utage game root and overwrite. Fully close RPCS3 and
cold boot m034/pl015 without a save state. Compare the same two-line Katakura
and three-line Masamune exchanges: the panel must remain where V18 placed it,
while the whole glyph block should move upward to the SH baseline. Also verify
portrait, name plate, mission banner, health/Basara meters, partner HUD, map,
and KOs counter.
