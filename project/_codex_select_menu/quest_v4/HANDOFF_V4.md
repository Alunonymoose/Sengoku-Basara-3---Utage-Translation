# Latest menu state: V4 installed

All 22 archives installed and read back successfully. See release/INSTALL_RESULT.json.
Package SHA-256: 79ce684c869a47a06bd0d516d1a0368d55744a0703f7227aa054ecd6ffce8c4b

V4 supersedes V3's charasele encoding and adds the missing actual main-menu atlas.
The main menu uses mode_select_000, including eng/init_ps3.arc entry9, title.arc
entry318 and title_id.arc entry143, plus eleven other English archive-local copies.
Both normal/right and selected/left texture columns were patched in all fourteen.
All first-five old text slots were cleared and replaced within the original UVs.
Nine charasele copies were re-encoded from clean approved sprites. All old lettering
pixels in edited slots are overwritten; zero opacity leakage passed all19 cell tests.

Important BC3 defect: the prior shared encoder replaced color0 with color1+1 when
endpoints were reverse ordered, losing a real colour endpoint. V4 swaps correctly
and retains an explicit zero-green/zero-opacity palette endpoint when needed.
The local codec_v4.py fixes this without changing Claude's shared tools. Do not
rebuild these coloured textures with the previous encoder.

The lingering currency owner included rom/battleQuest.arc and startup title.arc;
those plus retry/save currency cells now use the actual official English Z.
Every numeral cell is preserved.

Independent audit: 27 changed resources, 1643 untouched compressed resources,
51 unchanged LSPs. All changes stay in declared texture cells. Backup is beside
package. All original Japanese-reference and active Claude message files untouched.

The user still needs to cold-boot and confirm in-game. No runtime success is claimed.
The last process check found RPCS3 closed. Do not confuse decoded previews with
screenshots from a new game run. Continue from current live archives, not V3 backups.
