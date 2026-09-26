# Runtime issues from the user's screenshots (2026-09-26, after the texture installs)

The screenshots are from after the propagate parts 1–3 and the waza2 repair. They cover:
- the BASARA Mart (Unification);
- a mission card (Kubota);
- in-battle name tags;
- the pause menu.

| # | Seen | Scope | Root cause (evidence level) | Universal fix |
|---|---|---|---|---|
| 1 | Latin text drawn with wide, even letter spacing. "Tale of the Wandering Road" runs past its bar and over the price; the shop description, mission card body, pause stage name and "defeated / KO'd" lines are the same | **every GSM text box** | Suspected: the TNF advance of Latin glyphs is full cell width, not glyph width (not yet proven: no TNF bytes in the cloud yet) | `pack_members.py --fonts` packs every distinct TNF/CSA/font page. Then one metrics rule for every TNF (advance = ink width + spacing), applied as a patchset to all font owners and checked against `basara.font.measure` budgets |
| 2 | 回 beside the lottery ticket count (BASARA Mart) | `tenka_009` (4 archives) | Japanese left in the texture (review: NEEDS_NEW_ENGLISH_ART) | New-art batch |
| 3 | "Player 1 \| P…" tag cut off and overlapping, pause menu | `common_013` (Partner) | Japanese パートナー tags + layout | New-art batch |
| 4 | "173 Hits!" with a squashed, garbled "Hits!" | cockpit/pause combo counter texture | Unknown: not in the language-keyed review set | Identify the member (`--all` audit) |
| 5 | Magenta glow on enemy name tags ("Defense Post Chief", "Satake Army Soldier") | `cp_name_*` families | Candidate: the same missing-prefill fault as waza2 | `chroma_audit.py`, whole game, with approval boards |

Tools added for this round (all read-only on the game until an approved install):
- `tools/chroma_audit.py`:
  - classifies every edited 0x2A texture (MISSING_PREFILL / OPAQUE_CANVAS / SWAPPED / OFF_NEUTRAL / OK);
  - builds the deterministic neutral-chroma repair and the before/after boards for MISSING_PREFILL;
  - writes `REPAIR.tsv` for `replace_members.py`.
  - Validated on the real waza2 bytes: 23 of 29 detected automatically, the other 6 flagged for review, and all 29 repaired versions classify OK.
- `tools/pack_members.py --fonts`.
- The new-art inputs list: one live provider of each of the 56 textures that still show Japanese outside `brief/og/`, plus the 3 result labels and `title_005`.
