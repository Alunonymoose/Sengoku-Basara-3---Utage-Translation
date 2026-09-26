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
