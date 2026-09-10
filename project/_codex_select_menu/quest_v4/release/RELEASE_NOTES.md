# V4 - startup/main-menu ownership and clean texture encoding

V4 is a focused update on the installed V3 menu work. It changes 27 texture
resources in 22 archives and preserves 1,643 other compressed resources and all
51 layout resources byte-for-byte.

The five user-approved coloured designs are now in mode_select_000's normal and
selected slots, synchronized across all 14 English copies, including init_ps3.arc,
title.arc and title_id.arc. Gallery/Options and other lower rows keep their existing
English artwork. No other resources in the gallery or option archives are edited.

Nine charasele atlas copies are re-encoded with the corrected local BC3 encoder.
The old encoder discarded one colour endpoint when its numeric order was reversed;
V4 swaps the endpoints and explicitly preserves zero-opacity background pixels.
Full target cells start blank, then receive the cleaned approved lettering. All
Japanese/old English pixels within those cells are overwritten. Detached specks
are removed from the approved masters. This pass introduces no new designs.

Four additional currency cells are replaced with the actual official English Z,
including shared rom/battleQuest.arc and the title-startup copy. Numerals remain
unchanged. The root shared archive is intentionally included; it is a runtime
quest resource, not a Japanese-reference file.

Independent verification passed: all changed blocks remain within declared cells;
all 19 rebuilt lettering cells have zero visible or faint opacity outside the
clean source artwork; every original non-target compressed resource is preserved.
No msg_* dialogue, tenka_msg000/001, demo or Japanese-reference archive was changed.

This is an offline-validated candidate. Cold-boot RPCS3; check the first five main
menu options in normal and selected states, enter Japan's Event, inspect the
heading on the light background and check the reward currency. Do not reload an
old emulator save state. No in-game verification is claimed.

The package merges into the existing patched game root. It is a focused update,
not the full game or full English patch. BACKUP_PRE_V4.zip is the rollback snapshot.
