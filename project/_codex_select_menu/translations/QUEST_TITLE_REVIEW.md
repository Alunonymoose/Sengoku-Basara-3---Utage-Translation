# Quest title translation review

Reviewed 2026-09-08. Scope: the 31 quest title textures in `rom/eng/select/c_common.arc`, entries 31-61. The Japanese transcription below was read from the supplied extracted source textures and contact sheets. English wording was read from existing localized textures in the working game. No game archives were modified by this review.

## Implementation recommendation

Reuse the existing 31 localized quest textures from `rom/eng/quest/q000_id.arc` through `q030_id.arc`, entry 0. Every resource has the same name and a 512 x 128 DXT5 texture with a 20-byte XET header and 65,536-byte payload. All 31 donor payloads exactly match their corresponding resources in `rom/eng/quest/quest_id.arc`. There are no `quest_000`-`quest_030` title resources in `rom/eng/quest/menu.arc`.

The corresponding 31 textures in `rom/eng/tenka/quest_q000.arc` through `quest_q030.arc` are still Japanese and exactly match the select sources. They are not English donors.

Use the existing wording unchanged for this select-only repair. This keeps the select screen consistent with the already localized quest menu. `quest_001` has an inherited translation issue, described below; correcting only the select copy would create inconsistent titles.

## Ledger

The number shown in the game is the texture index plus one. Both visual rows of each texture repeat the same title; capitalization below matches the existing donor artwork.

| Texture | Shown | Japanese title | Existing English donor wording | Review |
|---|---:|---|---|---|
| quest_000 | 01 | 戦国訓練所 入門編 | SENGOKU TRAINING: BEGINNER | Accurate concise rendering. |
| quest_001 | 02 | 紳士の決闘 | SWORDSMAN'S DUEL | Inherited semantic mismatch: 紳士 means gentleman, not swordsman. A future synchronized wording fix could use GENTLEMEN'S DUEL. Keep the donor wording for this select consistency repair. |
| quest_002 | 03 | 初心者卒業試験 | BEGINNER GRADUATION EXAM | Accurate. |
| quest_003 | 04 | 戦国技能検定 仮免 | SENGOKU SKILL TEST: PERMIT | Concise adaptation of provisional license. Distinguishes this stage from the full license below. |
| quest_004 | 05 | 真夜中の香り | MIDNIGHT SCENT | Accurate. |
| quest_005 | 06 | 多士済々のすゝめ | A WEALTH OF TALENT | Concise adaptation: the original encourages a gathering/abundance of talented people. |
| quest_006 | 07 | 戦国訓練所 中級編 | SENGOKU TRAINING: INTERMEDIATE | Accurate. |
| quest_007 | 08 | 名城めぐり | FAMOUS CASTLE TOUR | Accurate. |
| quest_008 | 09 | 花鳥諷詠 | NATURE IN VERSE | Appropriate idiomatic translation of poetic celebration of nature. |
| quest_009 | 10 | 戦国技能検定 本免 | SENGOKU SKILL TEST: LICENSE | Concise adaptation of full license. |
| quest_010 | 11 | 兵種のるつぼ | TROOP TYPE MELTING POT | Accurate, though literal. |
| quest_011 | 12 | 戦国未来博 | SENGOKU FUTURE EXPO | Accurate. |
| quest_012 | 13 | 戦国訓練所 上級編 | SENGOKU TRAINING: ADVANCED | Accurate. |
| quest_013 | 14 | 宵闇の羽 | WINGS OF TWILIGHT | Suitable poetic adaptation; 羽 can mean feathers or wings. |
| quest_014 | 15 | 海賊捕物帖 | PIRATE MANHUNT | Concise adaptation of a pirate capture/arrest chronicle. |
| quest_015 | 16 | 百獣の女王 | QUEEN OF BEASTS | Accurate. |
| quest_016 | 17 | 新旧交代の狼煙 | CHANGING OF THE GUARD | Appropriate idiomatic adaptation. The original adds a signal/beacon for the old-to-new succession. |
| quest_017 | 18 | 俺たち乱破衆！ | WE'RE THE SHINOBI! | Appropriate adaptation of the ninja/raider group title. |
| quest_018 | 19 | 愛の方程式 | THE LOVE EQUATION | Accurate. |
| quest_019 | 20 | 円熟のロマン | MATURE ROMANCE | Plausible concise adaptation; ロマン has a broader romantic-ideal sense than a love affair alone. |
| quest_020 | 21 | 戦国女子会！ | SENGOKU GIRLS' NIGHT! | Natural adaptation; the Japanese specifies a women's gathering, without explicitly specifying night. |
| quest_021 | 22 | 以心伝心闘争心 | HEARTS IN SYNC, READY TO FIGHT | Good idiomatic treatment of the paired phrases for tacit understanding and fighting spirit. |
| quest_022 | 23 | 棚ボタ大作戦 | OPERATION LUCKY BREAK | Good idiomatic adaptation of an unexpected windfall. |
| quest_023 | 24 | 戦国最強決定戦 | SENGOKU STRONGEST SHOWDOWN | Accurate concise rendering. |
| quest_024 | 25 | 降魔地獄変 | DEMON-QUELLING INFERNO | Suitable compressed, stylized adaptation of the demon-subduing hell title. |
| quest_025 | 26 | 梟雄の軌跡 | THE SCHEMER'S PATH | Plausible adaptation; 梟雄 suggests a ruthless/cunning formidable leader, not merely a schemer. |
| quest_026 | 27 | 悶絶！！武田道場 | AGONY!! TAKEDA DOJO | Accurate stylized rendering. |
| quest_027 | 28 | 鋼鉄の戦神 | STEEL GOD OF WAR | Accurate. |
| quest_028 | 29 | 婆娑羅英雄列伝 | BASARA HERO CHRONICLE | Suitable franchise-term rendering and concise adaptation of collected hero biographies/tales. |
| quest_029 | 30 | 煉獄と地獄 | PURGATORY AND HELL | Accurate. |
| quest_030 | 31 | 戦国大宴会 | SENGOKU GRAND BANQUET | Accurate. |

## Evidence files and limits

- `EXISTING_QUEST_DONORS.json`: the 31 live donor paths, resource names, XET dimensions/format, raw SHA-256 values, and equality results against the combined quest archive.
- `EXISTING_QUEST_ENGLISH_REFERENCE.png`: contact page rendered from the existing English donor textures.
- Source images: `../source/c_common__031__quest_000_ID_HQ.png` through `../source/c_common__061__quest_030_ID_HQ.png`.

All English suggestions here are based on actual project assets and the supplied Japanese text. No claim is made that these are official published English quest titles. Japanese punctuation and spacing are normalized in the ledger. Texture reuse still needs the parent task's layout/UV, archive-scope, and visible-render verification; this report does not establish runtime fit.
