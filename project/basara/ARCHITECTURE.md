# basara — architecture and engineering direction (2026-09-26)

> **SCOPE CORRECTION — 2026-09-26 (user tasking: Drive `BASARA Foundry — Frontier AI Tasking for Remaining Texture & Dialogue Work — 2026-09-25`).**
> The game principally needs **texture work and dialogue work**, not more architecture. `basara` is
> **feature-frozen**: no TMS, orchestration layer, provenance platform or new subsystems. It exists to
> serve the corpus pass — its decoders (`arc`, `msg`, `font`, `xet`), the censuses and the safe
> `install` are the "small helpers" that pass needs. `patch`/`catalog` stay as they are and grow only
> when a real texture or dialogue job needs it. The next session's job is the corpus archaeology
> (`project/skills_updates_2026-09-25/utage-corpus-archaeology/SKILL.md`), not this codebase.

## 1. What was wrong (measured, not opinion)

| Finding | Evidence in this repo on 2026-09-26 |
|---|---|
| No shared library: every job re-implemented the formats | ~20 separate ARC parsers, 23 XET/TEX readers, 9 BC block decoders, 17 GSM parsers, 19 FIM handlers, 18 TNF/CSA readers across 35k lines of Python (plus 12k lines of C#) |
| Copy-paste versioning instead of source control | `project/_codex_select_menu/quest_v2` … `quest_v11`: ten folders of near-identical build scripts |
| Format truth lived in prose, and the prose drifted | the 2026-09-23 "PS3 big-endian BC endpoint" rule shipped mis-coloured textures for two days; two incompatible FIM contracts (0x8000 vs 0xD000 glyph limit; different speech splitting) coexisted in "canonical" tools |
| Fixes stranded on side branches | the title_004 endian hotfix sat on an orphan branch while the primary branch kept the bug; `foundry-v0.1`, `foundry-v0.2-orchestration` and the hotfix branch share no merge base |
| Validation that could not fail | identity patches never call the encoder; encoder→own-decoder round trips agree with themselves |
| Every change was a bespoke script + a ZIP or a hand copy | no declarative description of *what* a patch changes, so nothing could prove *only* that changed |
| Full inflation just to list an archive | `safe_arc.parse_arc` decompresses every member; indexing 11,279 live ARCs is dominated by that cost |

## 2. Principles

1. **One implementation per format.** Tools import `basara`; they never parse bytes themselves.
2. **Exact round trip or refuse.** Every parser has a builder; untouched bytes stay untouched and that is tested.
3. **Contracts are code, not prose.** The FIM contract, the grammar table and the XET format table are enforced by the library and exercised by property tests. Docs describe; code decides.
4. **Detect, don't assume.** Grammar is detected per table (zero violations on the untouched table or fail closed); texture byte order is measured before any write.
5. **Declarative changes.** A patchset says what changes, bound to exact input hashes and approved candidate hashes. The engine proves nothing else changed.
6. **Tests that can fail.** Differential tests against an independent oracle (`safe_arc`), display-space colour regressions, and property tests over random edits.

## 3. Module map

| Module | Responsibility | Replaces |
|---|---|---|
| `arc` | ARC v8 strict read, lenient `inspect`, lazy inflation, rebuild, verify, fixture builder | `safe_arc.py`, `arc_tools.py`, ~18 inline parsers |
| `xet` | XET decode/encode, 0x2A YCbCr, block graft, byte-order evidence, legacy scan | `utage_xet.py` (now a shim), `xetenc.py`/`xet3.py` (quarantined), 22 inline readers |
| `msg` | GSM/FIM models, grammar tables + detection, FIM contract derive/check/apply | `gsm_tools.py`, `FIM_CONTRACT_REPAIR.py` contract code, 17 inline GSM parsers |
| `font` | TNF metrics, CSA maps, per-line width | TNF/CSA code in census/quest scripts |
| `markup` | lossless human-editable text ↔ words | `decode_words_ascii`/`encode_text` (lossy, one-way) |
| `psl` | PSL nodes, dest/source rects | `layout_census.py` parser, `inspect_psl_nodes.py` |
| `table` | one message table edited as text with the contract kept | per-job GSM/FIM rebuild code |
| `patch` | patchset build / install / rollback | quest_vN build scripts, ROOT-READY ZIPs, hand installs |
| `catalog` | TSV export / lint / import | ad-hoc TSVs, manual review |
| `cli`, `texcli` | `basara …` | `xetcli.py` (now a shim), dozens of one-off CLIs |

## 4. Decisions

**D1 — FIM contract.** Adopted the `FIM_CONTRACT_REPAIR` rule (glyph = word < 0x8000; speeches start after each 0xFFFD except the terminator; col1-high = speech start). It is the one validated with zero exceptions on 1.47M pristine JP + 246k official SH rows. `gsm_tools.reveal_budget` (0xD000 limit, drops text after the last 0xFFFD) disagrees on words 0x8000–0xCFFF and on records without a trailing delimiter. `check()` reports `ambiguous_words` so a live census settles the 0x8000–0xCFFF question with data.

**D2 — Grammar.** `WESTERN` (FF92:1, FF91:0, FC0D:1, FC0E:2, FC17:3) is the corpus grammar; `LEGACY` (FF92:2, FF91:1) exists only so detection can prove which a table uses. Unknown control words fail closed.

**D3 — CSA.** One description: u16 table at byte 8, indexed by codepoint (cp ≥ 12). The "offset 32, cp+12" wording is the same table (tested).

**D4 — Textures.** Standard BC payload byte order; 0x2A = BC3 + YCbCr, neutral chroma 123. The byte order is runtime-proven; the decode constants are confirmed in Capcom's own compiled shaders (`project/texture_tools/GAME_SHADER_GROUND_TRUTH_2026-09-26.md`). Multi-image XETs (cube maps) are refused. See `project/texture_tools/TEXTURE_PIPELINE_CANON_2026-09-25.md`.

**D5 — Installs.** No ZIPs. `basara install` = verified backup → hash-guarded atomic replace → read-back → record. Rollback never erases later edits. This is the 2026-09-25 user hard rule, as code.

**D6 — Python is the engine; C# Foundry is the UI.** The C# codec is kept correct (hotfix ported), but new format work lands in `basara` first. The WinUI app should shell out to `basara … --json` rather than grow a second implementation.

**D7 — safe_arc stays pinned as a test oracle** until every consumer has migrated; `basara.arc` is proven byte-identical to it by a differential property test.

## 5. Migration plan (retire, don't delete)

| Step | Owner action | Done when |
|---|---|---|
| 1 | Run `basara msg census` and `basara tex census --ref` on live E: | both JSONs in `E:\BASARA_AUDITS`; every UNCHARTED table and flagged texture has a ledger row |
| 2 | New text/texture work only through catalogs + patchsets | no new `quest_vN`/`build_*.py` scripts appear |
| 3 | Point `foundry-v0.2` snapshot indexing at `basara.arc.inspect` (lazy) | snapshot of live E: runs in seconds per 1k ARCs |
| 4 | Point release audit (`message_census`, `font_contract_census`, `layout_census`, texture export) at `basara` | pinned-path imports of `safe_arc`/decoder removed |
| 5 | Move `_codex_*`, `Alrummi3`, dated tool folders under `project/legacy/` with a README | top of `project/` shows only live tooling |
| 6 | Merge one integration branch into `foundry-v0.1`; stop orphan histories | every branch shares history with the primary branch |

## 6. Roadmap

* **Widget budget registry** — a versioned table of measured line budgets per widget family (equip description 700×2, Mart bar 686–702×3, ticker 574, …) that `catalog lint` and `build` load automatically instead of `--budget`.
* **Owner-aware patchsets** — resolve every co-resident provider of a resource from the v0.2 snapshot DB and apply lockstep automatically (today: listed explicitly and verified identical).
* **Translation memory** — reuse approved strings across tables (`id_brief` / `id_brief_r`, pause `waza_pl`, `tenka waza_name`) and flag inconsistent renderings of the same Japanese source.
* **Runtime evidence binding** — `basara install` writes the build id the v0.2 runtime matrix expects, so a cold-boot screenshot is bound to exact bytes.
* **Mip-chain + BC1/BC2 writers** — only with a real fixture and a cold boot each.
