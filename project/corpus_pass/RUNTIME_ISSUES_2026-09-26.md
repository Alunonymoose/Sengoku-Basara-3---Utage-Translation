# Runtime issues from the user's screenshots (2026-09-26, after the texture installs)

The screenshots are from after the propagate parts 1–3 and the waza2 repair. They cover:
- the BASARA Mart (Unification);
- a mission card (Kubota);
- in-battle name tags;
- the pause menu.

| # | Seen | Scope | Root cause (evidence level) | Universal fix |
|---|---|---|---|---|
| 1 | Latin text drawn with wide, even letter spacing. "Tale of the Wandering Road" runs past its bar and over the price; the shop description, mission card body, pause stage name and "defeated / KO'd" lines are the same | **every GSM text box** | **Disproved:** the TNF advances are already proportional. fonts_part01 has 32 distinct TNFs; the ascii TNF df843e0b (26x20 cells, 184 glyphs) gives a=13, i=7, W=19 and is shared under 1,430 table names. The screenshot shows monospace (i, l, W all about 20 px at 720p), so **the game ignores the TNF advance in these windows**. Mechanism still open | Compare with Samurai Heroes (official English, proportional). Run `pack_members.py --fonts` on the SH rom, then diff the TNF header flags, the CSA and the GSM/PSL window attributes. No TNF edit until the switch is found by bytes |
| 2 | 回 beside the lottery ticket count (BASARA Mart) | `tenka_009` (4 archives) | Japanese left in the texture (review: NEEDS_NEW_ENGLISH_ART) | NEWART_BATCH1: 10%/20%/50% OFF, FREE, SOLD, pg; 回 erased; 弐 → 2 (after 99adf901…) |
| 3 | "Player 1 \| P…" tag cut off and overlapping, pause menu | `common_013` (Partner) | Japanese パートナー tags + layout | NEWART_BATCH1: both tags → "Partner" (after 2305199…); also tenka_finish_id#74 (same JPN source, different ENG base) |
| 4 | "173 Hits!" with a squashed, garbled "Hits!" | cockpit/pause combo counter texture | Unknown: not in the language-keyed review set | Identify the member (`--all` audit) |
| 5 | Magenta glow on enemy name tags ("Defense Post Chief", "Satake Army Soldier") | `cp_name_*` families | **Confirmed, a different class: MAGENTA_CAST.** The texels are opaque with a Cr/Cb magenta shift where JPN is achromatic: name 30, cp_name_nak 19, title_005 1 (title_005 also has grey luma, so it is excluded and needs new art) | `chroma_audit.py` now classifies MAGENTA_CAST as repairable: Cr/Cb go to 123, and Y and A are kept |

Tools added for this round (all read-only on the game until an approved install):
- `tools/chroma_audit.py`:
  - classifies every edited 0x2A texture (MISSING_PREFILL / OPAQUE_CANVAS / SWAPPED / OFF_NEUTRAL / OK);
  - builds the deterministic neutral-chroma repair and the before/after boards for MISSING_PREFILL;
  - writes `REPAIR.tsv` for `replace_members.py`.
  - Validated on the real waza2 bytes: 23 of 29 detected automatically, the other 6 flagged for review, and all 29 repaired versions classify OK.
- `tools/pack_members.py --fonts`.
- The new-art inputs list: one live provider of each of the 56 textures that still show Japanese outside `brief/og/`, plus the 3 result labels and `title_005`.

## Audit result (fonts_part01 + upload_part01, 2026-09-26)

- 916 edited 0x2A textures:
  - 664 OK;
  - 230 OFF_NEUTRAL, of which 50 are MAGENTA_CAST and the rest are intended colour designs;
  - 19 MISSING_PREFILL (army_000–016/022/026; repaired luma error max 12–17);
  - 3 OPAQUE_CANVAS (result_000/023/026, which need new art).
- Repairable classes are `MISSING_PREFILL` and `MAGENTA_CAST`. The user re-runs `chroma_audit.py` with this commit to get the boards and `REPAIR.tsv`.

## New-art tool

`tools/label_candidates.py SPEC.json --out DIR` builds deterministic label candidates on a copy of the real decoded live member:
- `clear` modes: interp / transparent / text-predicate.
- Text is rendered at 4x.
- Candidates are refused unless `unchanged_outside_mask`.
- Grafts use prefill=dilate.
- Output: a board of JPN | live | candidate, where the candidate panel is decoded from the encoded bytes.

A batch installs only after approval, via `replace_members.py` (before/after sha re-proven), then `basara build` / `basara install`. Batch 1 is tenka_009 and common_013 (7 member rows); the specs stay off GitHub because they hold game text.

## Round 2 evidence (2026-09-26: audit2 + Samurai Heroes fonts)

**Letter spacing: the cause is not in the font data.**
- SH's whole rom has exactly one font set, in `eng/basara.arc`. Its TNF, CSA and both atlas pages are byte-identical to Utage's (df843e0b / 9d5b4932 / bd9325a9 / 2563fb5f).
- `msg\font` (rFontColor, `\0LCF`) is an identical 8-colour palette in both games.
- `ascii_0N_ID_HQ` rPalette (`\0TLP`, v1) is also identical.
- The dialogue window is proven proportional (HANDOVER 2026-08-31 §5: "Masamune" advances 17/12/12/12).
- So the same font renders proportionally in one window and monospace in others. The per-window difference has to come from:
  - the layout: `sBasaraLayout` picks `id\lsp\jpn` (Utage) or `id\lsp\abr` (SH's Western masters, identical in all 5 languages);
  - or the EBOOT.
- Next step, by bytes: `pack_members.py --layouts` on SH eng and Utage eng, then a node-by-node diff of the menu/shop/brief/pause LSPs by stable node id. This follows the V16/V18 method; do not copy `+0x38` links.

**audit2: 48 MAGENTA_CAST + 19 MISSING_PREFILL = 67 distinct repairs, 78 REPAIR.tsv rows.**
- All 33 boards were checked by eye:
  - repairs are clean white/black on neutral;
  - the remaining OFF_NEUTRAL are intended colour designs: `result/plNNN` gold brush names, the approved `cp_name_pl`, quest cards, maps.
- The magenta `cp_name_nak` copies are only in `tenka/friend.arc` (#108–#162). The `id/friend_*`, `pause/friend_*` and `quest/*` copies were already neutral.
- The magenta `name_NNN` copies are only in `tenka/tenka_plNNN.arc#0`.
- Open: the in-battle "Defense Post Chief" tag is **not** among these. Every `cp_name_army_*` / `cp_name_han_*` texture is neutral. It is either a texture whose ENG and JPN copies are identical (the audit skips those, because the jpn tree was also patched) or an engine tint. It needs its archive and member identified from the mission it was seen in.

## Install record: audit2 repairs (2026-09-26T19:42:41Z), INSTALLED, not RUNTIME_TESTED

- `basara install`, patchset `repair-20260926`, build patchset sha256 `e4a4ef26c323b014…`.
- Backup: `C:\review\backups\repair-20260926_20260926T194241Z`.
- 78 members in 60 archives:
  - `result/pl000–029.arc#6` (army MISSING_PREFILL);
  - `tenka/friend.arc` (19 cp_name_nak);
  - `tenka/tenka_pl000–027,029.arc#0` (name MAGENTA_CAST).
- `replace_members`: 78/78 rows re-proven, 0 left out.
- Rollback order (newest first): this one, then part 3, waza2, part 2, part 1.
- The first `--layouts` pack of SH `rom\eng` held only 50 PSL. SH's HUD masters (`id\lsp\abr\…`) sit in root-level archives such as `rom\battle.arc`, so the comparison needs `--eng <rom>` (the rom root) for both games.

## Round 3 evidence (layouts + text corpus, 2026-09-26)

**The layouts do not carry text pitch.**
- The SH `abr` and Utage `jpn` LSP masters were diffed node by node (by name and occurrence) across 37 matched layouts: pause, option, soubi, tenka, top, result, gallery, cockpit and others.
- The non-geometry fields that differ are:
  - +0x48/+0x4C: texture size;
  - +0x30 / +0x70: flags;
  - +0x60: priority;
  - +0x94..: vertex colours;
  - +0x54: node type, on a few nodes.
- None of them is a text-spacing parameter, and message-type nodes are byte-identical apart from +0x30.
- Text is drawn by code at node positions.

**GSM encoding is the same as SH.**
- `id_tenka`, `id_pause` and `id_brief` in both games use the same control vocabulary (FFFF/FFFE/FF92/FF91/FC11), with no per-character codes.
- The font bytes are identical (round 2).
- So the fixed pitch in the shop, brief, pause and log windows is chosen by EBOOT code, most likely keyed on `mLanguage`. That is the same switch that picks `id\lsp\jpn` vs `id\lsp\abr` and `id\texture\jpn` vs `id\texture\eng`, and all of those paths are already in Utage's EBOOT (HANDOVER §3).
- The universal fix is therefore an EBOOT patch (an RPCS3 patch.yml entry): either flip `mLanguage` to the Western value, or patch the pitch branch. The next input needed is the decrypted `EBOOT.elf`.

**The in-battle name tags ("Satake Army", "Defense Post Chief") are font text, not textures.**
- They come from the per-mission `_r` table records 0–12 (e.g. `id/msg_m000_pl000.arc#18`).
- The records have no colour codes; the glyph pages are neutral and identical to SH.
- So the glow colour is applied by the engine per unit type and is probably the original design. Check a JPN screenshot of the same tag before treating it as a defect.
