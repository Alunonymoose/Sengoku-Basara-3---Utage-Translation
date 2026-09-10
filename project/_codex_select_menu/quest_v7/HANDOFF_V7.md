# Current V7 live state

Installed and byte read-back verified in E:\Utage Patching New. See release/INSTALL_RESULT.json and RELEASE_NOTES.md. 39 archives / 47 changed resources / 963 preserved compressed entries. Backup and root-ready package both verified.

This pass fixes the reported faint map mode heading, Player 2 strip under Player 1, fourteen map/result character names (016..029), Matsunaga's Forces copies, and visible first three shop item families. GSM_r records 332..335 rename Profitable Business to Profit Bonus. Records 532..543 translate Magnificence/Bumper Crop/Profit Bonus descriptions; control codes and restrictions preserved. Other GSM records unchanged. Many other shop/lottery strings remain Japanese and are not claimed translated.

Cold-boot visual verification still needed. Do not re-run build_v7.py after install: its input is the pre-V7 live tree and backup must be preserved. Any next iteration needs a new version folder and snapshot of current live archives. V7 changes only dedicated top_00 node89 scales (1.25,1.25), not common layouts. Header common_013 full player badges now use separate 64px rows; small badges restored from original read-only Japanese texture cells. Name alpha margins and bounded texture block edits passed independent verification.

Remaining relevant work: additional shop accessory/weapon descriptions and names, lottery ticket artwork/count wording, Japanese Partner labels in common_013. Item description mapping for the new equipment families has offset 208: name324 -> description532. Do not assume all records follow this offset. GSM_r contains1963 records including unrelated weapon and unit names. Native English font CSA lacks some punctuation; check glyph coverage before encoding. Question marks on locked stock are intentional.

Never touch Claude's eng/id/msg_*_pl*.arc or tenka_msg000/001.arc. Preserve all Japanese originals and demo exclusions. V6 Options and menu changes are runtime confirmed by the user's latest screenshots and remain intact.
