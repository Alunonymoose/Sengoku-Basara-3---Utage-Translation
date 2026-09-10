# Installed V5, 8 September 2026

User approved the colorful V4 designs but reported fuzzy/untidy lettering, distorted Versus, mismatched Gallery/Options, Japanese locked-character label, and broken red P2 prompt. V5 is installed in E:\Utage Patching New. See release/INSTALL_RESULT.json for 25 live archive hashes, package and rollback hashes. Runtime verification remains pending; RPCS3 was running and was not interrupted.

Use V5 as the current baseline. Do not rerun stage_v5.py against installed files: its backup guard intentionally requires the pre-V5 state. build_v5.py creates candidate textures only; package_and_install_v5.py also guards pre-install hashes. Keep the exact rollback archive.

Main menu was owned by fourteen mode_select_000 copies, including startup init_ps3/title. The first seven 112-pixel rows in both columns were rebuilt. Selected crop widths are 340/380/380/280/360/360/400 pixels. Use natural aspect ratios, never resize master sprites independently in X and Y. Seven native shadow offsets changed from (4,5) to (1,1.5) in the two mode-select LSP copies. Nine charasele heading atlases received the same five original mode designs with preserved proportions; player badges and other atlas cells were retained.

Locked label owner is charasele_02_lock_ID_HQ (1024x128), four copies. It is not the blank silhouette charasele_01_qqq. Clear the entire label texture and fit inside physical x192..832, matching the Name_l/Name_r dynamic UV slot.

P2 compact prompt uses common_00 nodes named 2P_IN and 2P_IN2. Former sample [0,192,128,224] clipped a longer startup instruction and placed it outside the frame. New UV [60,192,130,224], geometry [0,-16,70,16], position [22,0], existing 0.8 scale. Panel remains [-16,0], geometry width128, scale0.8. Its right edge86.4 contains text ending78. Seven layout copies updated. Six local common_000 instruction rows differed (including Japanese battleQuest); bounded physical row [0,384,512,448] now matches the startup atlas. Full instruction nodes retain their original layout. Static icon placeholder samples L2; runtime chooses START. The illustration uses the runtime START sample without changing native icon data or input behavior.

Independent parser verified 42 changed resources, 1788 preserved compressed resources and exactly 84 declared LSP float/int fields; texture block edits are bounded. Alpha-zero checks passed. Artwork notes preserve prompts and high-resolution masters. All original Japanese reference files, demo resources, msg_* dialogue, conquest message archives, reward names and quest title/star/counter fixes remain untouched.

Required next check: fully stop and boot the game, inspect all seven main menu items in both states, then Japan's Event locked character and red P2 Join banner before/after joining. Do not describe this as visually verified in-engine until new runtime evidence arrives.
