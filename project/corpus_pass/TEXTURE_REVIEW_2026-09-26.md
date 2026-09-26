# Texture review: every language-keyed texture, classified (2026-09-26)

**Input:** the user's `texture_sheets.py` run on live `rom/eng` vs `rom/jpn` (one upload part,
63 contact sheets plus `texture_index.json`). That covers **47,314 language-keyed texture providers,
de-duplicated to 1,890 unique images**. Every tile was inspected by eye. Ambiguous tiles were
enlarged, and every call was cross-checked against the index hashes and owners.

The full per-texture atlas is not stored here, because it transcribes game text. It is
`TEXTURE_ATLAS_2026-09-26.tsv`, sent to the user and summarised in Drive. Each row carries:
tile, class, action, member, size/format, owners (`arc#index`), English twin tiles, note and sha256.

## 1. Result

| Class | Unique textures | Meaning |
|---|---|---|
| English | 824 | done |
| No text | 649 | art, faces, icons, frames, digits |
| Font pages | 164 | glyph atlases used by the text renderer (not visible labels) |
| Empty / crest / logo | 14 | blank sheets, the Ishida/恋/風 crests, the 宴 title kanji (design, keep) |
| **Japanese still visible** | **155** (237 owner slots) | see §2 |
| **English but damaged** | **33** | see §3 |
| English, QA issue | 51 | see §4 |

That is 155 of 1,890 unique images, about 8%. The live text tables are already 99.93% English,
so **these textures are the main thing left between the game and 100% English.**

## 2. The Japanese that is left: most of it already has an English version

Grouping the 155 Japanese textures by member name against the English ones gives this:

| Action | Unique | Examples |
|---|---|---|
| **COPY_EXISTING_ENGLISH** | **101** | `stage_001`–`045` banners in `common/mission/mNNN.arc` (English in `tenka/tenka_stage_mNNN.arc`); pause move lists `waza_004`–`006`, `016`–`029` in `pause/waza_plNNN.arc` (English in `tenka/waza_name_plNNN.arc`); Dream Chance army plates `army_018`–`021` in `tenka/dream.arc`; `tenka_japmap_02`–`10`, `yuugi_quest_001`–`004`, `result_001/002/005/006/009`, `cockpit_002/005/022/025`, `mode_select_000`, `kakutoku_008`, `gallery_12`, `shogo_000`, `tenka_007`, `tenka_tassei_007`, `cp_kessen_001`, `common_010`, `charasele_00_000` |
| REPAIR_ENGLISH_DONOR_THEN_COPY | 3 | `result_000/023/026`: the only English versions (`result_id.arc`) are legacy-damaged (§3) |
| **NEEDS_NEW_ENGLISH_ART** | **51** | `story_00_00`–`07` chapter titles; quest cards `qu_m_003/009/014/023/030`; Tenka/Lottery `tenka_008/009/018/020/021/023/024/027`, `tenka_tassei_002/006/009`; unlock banners `kakutoku_000/001/004`; versus menus `kessen_011/012`; result plates `result_018/024/027`, `shogo_007`; orb plates `wepball_007`–`010`; select screen `charasele_00_002` (chapter labels), `00_004`, `04_lock`, `05_005`; `cp_name_army_023_b`, `024_a`; `cp_kessen_002`; `gallery_07`; `common_013` (Partner), `common_025`; `option_000` chips; `mission_054` leftovers |

**The copy group is the cheap win.** The English translators edited one provider of an image and
missed the others. `project/basara/tools/propagate_translated_textures.py` finds every such case
**by bytes**. It only copies when:
- the donor was translated from the identical Japanese image;
- the donor is undamaged;
- all donors agree on one English version;
- the donor's layout (PSL) is unchanged.

It then emits a normal `basara.patchset/1` (raw member copies bound by sha256), which goes through
`basara build` → `basara install` (verified backup, hash-guarded write). No new art is involved.
Anything ambiguous goes to `review.tsv`. The visual count of 101 is the upper bound; the tool's
byte proof decides the real number.

Caveat: 19 of the 101 exist only in `brief/og/mode_quest.arc` / `brief/og/mode_tenka.arc`, whose
English counterparts are `brief/mode_quest.arc` / `brief/mode_tenka.arc`. `og` looks like a folder
of original copies. If the game never loads it, those 19 are invisible, and the visible copy win is
**82**. Whether the game loads that folder has not been established.

**First real run (2026-09-26, the user's `plan.json`).** The scan found 123 groups where a Japanese
image had been translated in some archives and not others:

| Verdict | Groups |
|---|---|
| SAFE | 86 |
| conflicting English versions | 28 |
| donor layout changed (`result_id.arc` PSL) | 6 |
| donor flagged as legacy-damaged (`result_001`, `tenka_japmap_08`, `waza_004`) | 3 |

Cross-checking against this review showed that bytes alone are not enough. Some SAFE groups are not
translations at all:
- 19 `cp_nakama` eye strips;
- `cockpit_016`, `common_015`, `pause_003`;
- a font page (`m000_03_13`, coupled to its archive's TNF/CSA);
- `common_025`, whose English donor still shows 極.

The approved list was therefore built from **plan ∩ visual review**:
1. every target must show Japanese;
2. every donor must be a reviewed, clean English image;
3. conflicts are resolved to the same design family (the `tenka_stage` brush banners for
   `common/mission`, and `brief/mode_*` for menu copies);
4. partially translated providers of the same Japanese image (`mode_select_000` gallery copies,
   `kakutoku_008` in `pause/option.arc`) get the fully English version.

The result is **114 copies, 90 members, 79 archives** (22 of them in `brief/og/`). The tool's
`--pairs` mode re-proves every row on the live files before building. Font pages are now never
copied automatically.

**INSTALLED on live E: (2026-09-26T01:02:19Z), state INSTALLED / not yet RUNTIME_TESTED.**
- Patchset `propagate-translated-textures-20260926`, build patchset sha256 `dfe7059b…90d5`.
- **111 copies into 79 archives** via `basara install`; every archive has a verified backup in
  `E:\BASARA_BACKUPS\propagate-translated-textures-20260926_20260926T010219Z\`.
- `basara rollback` on that INSTALL_RECORD restores it.

`--pairs` re-proved each row on the live files and refused 3 of the 114. Those targets store the
same Japanese image under another name (`cockpit_005` = `result_011` in
`tenka/tenka_finish_id.arc#63`; `cockpit_022` = `result_021` in `result_id.arc#86` and
`tenka/tenka_finish_id.arc#77`). The tool now takes `target_member` / `donor_member` columns.

**Part 2 installed 2026-09-26T01:05:57Z:**
- 3 copies; `result_id.arc` → `a84ef2dc…`, `tenka/tenka_finish_id.arc` → `b8684957…`;
- backups in `…_20260926T010557Z\`.

**All 114 approved copies are live.** To undo everything, roll back part 2 first, then part 1.
Rollback only restores where live equals that install's output.

Live hashes that older notes quote are superseded. For example, `versus/menu.arc` is now
`95d4c5bb…` (was `ee9b0da1…`, the menu58 v3 state). Only members 2 and 49 (the stage banners)
changed; member 58 is byte-identical.

**Cold-boot checklist:**
- a story/free mission start banner;
- the pause move list for pl005/006/016–029;
- a Dream Chance battle (army plates, cockpit_025);
- a Tenka finish/result screen;
- the gallery menus (Install row);
- options/save menus (`kakutoku_008`).

## 3. English but damaged: exactly the canon's legacy-writer suspects

| Member | Archive | Symptom |
|---|---|---|
| `waza2_001`–`029` (29) | `select/c_common.arc`, `select/c_versus.arc` | magenta/green fringing on every glyph |
| `result_000`, `result_023`, `result_026` | `result_id.arc` | English on an opaque navy / magenta / dark-red block where the JPN original is transparent |
| `title_005` | `title.arc` | the "Sengoku BASARA" sub-logo decodes with a heavy magenta/green cast |

The waza2 and result_id labels are the 2026-09-24 xetenc writes named as suspects in
`TEXTURE_PIPELINE_CANON_2026-09-25.md` §6. This review confirms them visually.

The repair uses the canon's method:
1. recover the approved art with the legacy view;
2. re-graft it with the certified writer;
3. approve it, install it, cold boot.

The propagation tool refuses these as donors (`REPAIR_DONOR_FIRST`), so the damage cannot spread.

**Byte-level diagnosis (2026-09-26, the user's `pack_members.py` upload).** None of these is the
xetenc endpoint-swap pattern: every one is standard order.

- **waza2_001–029: missing prefill.**
  - Covered texels have neutral chroma (median Cr/Cb 123), but fully transparent texels were
    stored as (0,0,0,0) instead of (123,0,123,0).
  - BC3 shares colour endpoints across each 4×4 block, so edge texels are pulled off neutral. That
    is the magenta/green fringe; only 22–42% of covered texels are neutral (JPN: 100%).
  - Repair (deterministic): keep the stored luma Y and alpha, set Cr=Cb=123 (the JPN waza2 art is
    100% achromatic), re-encode with the certified writer and `prefill=dilate`.
  - Result: 100% neutral; luma mean error 0.2 levels (max 4); alpha max 9. The header is untouched.
  - Built as exact bytes with a before/after board for approval, then installed with
    `tools/replace_members.py` (re-proves before/after sha256 on the live files). 31 targets,
    including the `select/c_versus.arc` duplicates of 001/029.
- **result_000 / 023 / 026: opaque coloured backgrounds.**
  - The English text was drawn on solid navy / magenta / dark-red canvases (alpha ≈ 245
    everywhere; the JPN originals are transparent).
  - The English lines also do not sit on the Japanese rows, while every result layout (`result_00`,
    `kakusyu`) is byte-identical to JPN.
  - Keying out the background would not fix the placement, so these go to the new-art batch (text
    laid into the JPN rows) after a runtime screenshot.
- **title_005: needs a runtime screenshot first.** Its luma is grey (median 85 vs JPN 255) and its
  chroma is off-neutral (148/145); the alpha channel carries the English logo shape. The intended
  look cannot be proven from the bytes alone.
- **tenka_japmap_08 (`brief/mode_tenka.arc`):** off-neutral (23%). It is only relevant to
  `brief/og`, so it is left as is.

**Held-back copies cleared:**
- `result_id.arc`'s only layout change is one node scale in `top_00` (0.95/0.90 → 1.25,
  6 bytes). `result_00` is identical in `result_id.arc`, `tenka_finish_id.arc` and JPN, so
  `result_002/006/009` can be copied.
- `result_001` and `waza_004` were legacy-scan false positives: their chroma is 100% neutral, which
  the legacy path cannot produce. `scan_against_reference` now clears that case
  (`cleared_by: neutral chroma`).
- These 5 copies make up part 3.
- QA: the English `result_006` rows do not map one-to-one onto the JPN rows. JPN row 8 is the
  reward-voucher line, where the English says "Fame Leveled Up!", and JPN row 14 has no English
  row. This is already the case in `result_id.arc`.

## 4. QA findings on English textures (not coverage, but visible)

- **Two English names for one character:** Josie / Joe C. Kuroda, Sunday Mouri / Mori,
  Saica / Saika, Kanbe / Kanbei.
- **Officer plates that disagree between variants:** Matabe / Matabei Goto, Fairlie / Fairy Muto,
  Yasukatsu Owafuri / Ohori, Akiyasu / Mitsuyasu Shimura, and more.
- **Typos:** "Picketpocket" (`cp_name_army_015_a`); "Kojiro Katakura" (lilac `name_023`).
- **Missing spaces:** "MasamuneDate" (`teki_name_032`); `cp_name_army_021` names run together.
- **Mismatched styles:**
  - two English title sets per quest (`quest_000`–`030`, e.g. "Swordsman's Duel" vs "Gentleman's Duel");
  - `army_026` in a serif font;
  - `cp_name_pl_028` in a small plain font, family name first.
- **Damaged renders:**
  - logo variants of `cp_name_pl_005/011/013/016`, where the alias line is illegible;
  - `cp_name_nak_025/026` squashed into a strip.
- **Legibility and glyph issues:**
  - thin white `stage_0xx` variants in `versus/menu.arc` are barely legible at review scale;
  - `yuugi_quest_001` label is truncated to "IGE /";
  - `id_title_05` font page draws Q–Z smaller and yellow-green.

## 5. Next actions, in value order

1. **Run `propagate_translated_textures.py`**, review `plan.json`, then build and install
   `safe/patchset.toml` with backups and cold-boot the listed screens. This is up to about 100
   textures of Japanese removed using art that has already shipped.
2. **Repair the 33 damaged textures** (waza2, result_id, title_005) with the certified writer, then
   run the propagation again (result_000/023/026 become copyable).
3. **New art for 51 textures**, grouped by screen (story chapter titles, quest cards,
   Tenka/Lottery, unlock banners, versus menus, orb plates). This follows the texture hard gate:
   live decode → edit mask → candidate → approval → graft.
4. The §4 QA fixes, together with the name-consistency pass (official SH names).
