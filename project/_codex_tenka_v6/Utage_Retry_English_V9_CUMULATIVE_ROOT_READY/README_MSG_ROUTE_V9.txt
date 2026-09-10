Sengoku BASARA 3 Utage English Patch - Message Route V9

Cumulative over V8. Merge PS3_GAME into the extracted game root and overwrite.

V9 routes the in-battle mission text onto Samurai Heroes' proportional ASCII text path.
Utage stored mission text as glyph indices into per-mission CJK atlases, which the engine
renders in fixed-width cells - the all-caps, wide-spaced, overflowing dialogue.
Samurai Heroes stores text as UTF-16BE code units offset by -33 (glyph = codepoint - 0x21)
resolved against msg\ascii\<lang>\ascii, which is proportional and mixed-case.

For each mission message set this replaces only the four text resources - GSM and FIM,
main and _r - with Samurai Heroes' English equivalents. Atlas pages, the descriptor and
every unrelated resource are preserved byte-for-byte. This mirrors Utage's already-working
id_result set, which keeps its atlas pages while using the ASCII encoding.

Mission sets converted: 608
Utage-only sets with no Samurai Heroes source (still Japanese): 802

A cold-boot gameplay test is required. Check in-battle dialogue for mixed case, proportional
spacing, and that lines fit inside the message box.
