# V8 current pass

User confirmed V7 shop appearance improved. V8 translates 40 accessories (GSM_r names248..287, descriptions456..495), including screenshot item282 Idaten Scroll / description490 movement speed. Installed with full live hash guards, backup, CRC checks, independent string decoding and read-back hashes. See release/INSTALL_RESULT.json. Three archives and four resources; all351 other compressed entries identical.

Do not rerun build.py against installed live files; it would overwrite the pre-V8 backup. Continue with a new version folder and snapshot. No textures or layouts changed. No protected dialogue/conquest/demo archives touched.

Remaining next batches: names208..247/descriptions416..455; names288..323/descriptions496..531; later accessory families336 onward. Confirm matching with native glyph render before using offset208. NAMES_208.png, NAMES_248.png and NAMES_288.png provide a broader name overview. Current translations.py has names248..287 and concise descriptions456..495. Some translated display names are compact localizations, not literal names. Existing alphabet lacks lowercase j/z and some punctuation; glyph coverage must be checked. Record489 carries red cost warning via FF92 argument2 / FF91 reset. Preserve controls in other descriptions rather than dropping them.

Runtime check pending for V8 after full RPCS3 restart. V7 look confirmed in screenshot, including no Player2 bleed and clear heading/name.
