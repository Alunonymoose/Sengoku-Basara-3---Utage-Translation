# GROK FORENSIC HANDOVER — SENGOKU BASARA 3 UTAGE
Date: 2026-09-20
Use case: independent adversarial analysis / code-pattern mining / cross-file comparison during parallel project work.
## ROLE
You are an independent forensic engineer reviewing an active PlayStation 3 English-localisation / reverse-engineering project for Sengoku BASARA 3 Utage (MT Framework Lite).
Your value is NOT to redesign UI art or rediscover generic MT Framework facts. Your job is to attack unresolved architecture questions, compare binary/resource patterns across large sets of files, challenge assumptions, and return evidence another engineer can immediately act on.
Treat every claim below as current project state unless you produce stronger contradictory evidence from supplied binaries/files. Distinguish PROVEN / STRONGLY SUPPORTED / HYPOTHESIS / DISPROVEN.
## PROJECT SOURCES OF TRUTH
GitHub:
Alunonymoose/Sengoku-Basara-3---Utage-Translation
Primary branch: foundry-v0.1
If repository access is available, read first:
1. .agents/skills/README.md
2. .agents/skills/basara-utage-core/SKILL.md
3. .agents/skills/basara-utage-texture-engineering/SKILL.md
4. project/dialogue_tools/fim_contract_recovery_2026-09-20/
5. project/checkpoints/UTAGE_24H_CROSS_CHAT_CHECKPOINT_2026-09-20.md if present
Google Drive canonical root:
BASARA Foundry
Read first if accessible:
1. 00 MASTER INDEX — BASARA FOUNDRY — READ FIRST
2. 00 Canon & Current State/00 READ ME FIRST — BASARA FOUNDRY / UTAGE MASTER SOURCE OF TRUTH
3. 00 Canon & Current State/00 24H CROSS-CHAT CHECKPOINT — 2026-09-20
4. 00 Canon & Current State/00 ACTIVE MASTER — READ BEFORE PATCHING/00 ACTIVE TITLE STATE GATE — 2026-09-18 — RUNTIME VERIFIED
5. 00 Canon & Current State/00 MSG-ASCII SYSTEM AUDIT — SB3 JPN → SAMURAI HEROES → UTAGE — 2026-09-20
6. 01 UTAGE TECHNICAL CANON — FORMATS, ROUTING, WORKFLOW, PROVEN FAILURES
Do not prefer chat recollection or filenames like FINAL/FIXED over those sources.
## CURRENT VERIFIED ARCHITECTURE
1. Patched EBOOT loads ENG title.arc then ENG title_id.arc before select/c_common.arc.
2. rom/eng/title_id.arc is the effective resident preload master for the synchronized charasele_02 character-name family.
3. charasele_02_000..029 is synchronized 210/210 across title_id, title, common/pl_face/pl_all, per-player pl_face, gallery, result, and tenka/get_pl.
4. common/pl_face/pl_all.arc is a synchronized stock-equivalent mirror of the title_id canonical set.
5. Runtime tests disabled physical rom/eng/common/pl_face and still rendered generic Unification Character Select correctly.
6. A/B tests neutralized charasele_02_003 in title.arc or title_id.arc independently: either resident preload could satisfy the existing same-name key.
7. Full-family diagnostic neutralized 86 pl_all-equivalent registrations in title.arc while normal title_id remained. Generic Character Select still rendered correctly with no physical common/pl_face access.
8. pl_all.arc has 112 entries; all 112 exist byte-identically in title_id.arc; 86 also exist in title.arc.
9. Therefore title_id is PROVEN as sole resident provider for the tested existing pl_all-equivalent family on generic Unification Character Select.
10. It is NOT YET proven that title_id can be deliberately expanded to arbitrary new resource families or that every screen resolves resident keys identically.
## CHARACTER-NAME SYSTEM WARNING
Do not conflate:
- select/c_story.arc cp_name_pl_000..029; versus
- generic Character Select charasele_02_000..029.
cp_name_pl is real and mapped, including stacked 256x128 slots 005/011/013/016 with lower alternate states, but c_story cp_name_pl was ruled out as the visible owner for the generic Character Select/Gallery nameplate issue being debugged. friend_003.arc and vs_cockpit.arc were also ruled out for that owner path.
MSG-side cp_name texture work synchronized 374 cp_name_pl instances across 356 mission ARCs using official Samurai Heroes donors. If the Nanbu battle plate remains wrong after that, investigate cockpit1P Name-node / UV/layout sampling rather than assuming the donor texture itself is wrong.
## MSG / FIM CURRENT AUTHORITY
Do not revive old theories.
- “m005 is short by 138 primary rows” is DISPROVEN.
- Current runaway-dialogue root-cause authority is the September 14 FIM contract.
- Production regeneration must rebuild FIM column 0 and column1.high16 consistently.
- Recovered production grammar includes FC17 = 3 and FF91 = 0.
- Separator fix was hardware/runtime proven across 1,287 archives / 1,590 slots.
- A 1,379-archive recovery ledger exists.
- m999’s 30 archives were intentionally skipped/untranslated in that recovered production pass.
- old msg_edit.py is superseded/quarantined.
- SB3 JPN ↔ Samurai Heroes yielded 608 localisation pairs, but direct SH GSM transplant / global SH ASCII replacement is NOT the correct general model.
- Pristine Utage structure remains authoritative; SH is a donor/contract reference.
- EVS/EVS2 restoration is not release-critical unless a live surface proves otherwise.
Important live fixture:
rom/eng/id/msg_m019_pl003.arc / msg\m019_03\jpn\m019_03 contains the Nanbu broken dialogue-plate case around GSM row 501. A relevant compared control/speaker difference was current 0002 vs SH 0001.
The dialogue-runaway logic is considered solved, but visual parity is not: dialogue-box text is still visibly too high relative to Samurai Heroes.
## WESTERN FONT / ASCII MODEL
The current correct model is hybrid, not global replacement:
- preserve Utage eng/jpn loaders and local structure;
- use verified Samurai Heroes TNF / CSA / ASCII atlas contracts and localisation-side LSP/FIM deltas where the bundle matches;
- do not copy only atlas XETs;
- do not replace every Utage text resource with SH.
Gallery’s SH TNF/atlas contract is runtime visually verified and should be treated as a known-good fixture.
Verified Gallery V1 gallery.arc:
size 771643 bytes
SHA-256 02c145fabae208c638576b8e116103c52fe4d47db4b2e334139641e8ec91b02e
Tenka is not automatically proven by Gallery.
SH tenka_id.arc is not a simple direct source of local id_tenka_00/01 replacements; localisation depends on GSM/FIM/Western LSP/textures plus global ASCII resources.
## TITLE TEXTURE CHANNELS — SOLVED
Do not spend time rediscovering title_004 unless contradictory binary evidence appears.
For PS3 XET/TEX 0x2A used by title_004:
G = coverage
A = Y
R = Cr
B = Cb
Global neutral chroma is a failed strategy.
The accepted clean-edge Sengoku repair preserves antialiased alpha, preconditions transparent RGB with the Sengoku blue, then performs correct 0x2A conversion / BC3 encoding and certified block grafting.
## BEST HIGH-VALUE ASSIGNMENTS FOR YOU
### ASSIGNMENT A — PROVE OR DISPROVE EXPANDABLE TITLE_ID AUTHORITY
Question:
Can title_id be deliberately extended into a general resident UI-resource library for resource families that were NOT already resident in title/title_id?
Do static analysis first:
- inspect title.arc / title_id.arc ARC tables, SCRA/rArchive registrations, internal path strings, resource keys, load ordering clues, and any EBOOT/ELF resource registration/lookup code available;
- identify whether lookup is keyed by normalized internal path, basename/resource-name hash, type+name, registration order, archive-local namespace, or another mechanism;
- explain why changing the title_id rArchive alias rom\eng\common\pl_face\pl003 -> zz003 did not break the tested charasele_02 resource;
- identify what exact metadata must be duplicated or altered if adding a genuinely new family to title_id.
Then propose ONE decisive runtime experiment using a family not already in title/title_id. Give exact donor member(s), original owner, title_id insertion path, local-owner neutralisation step, expected log behavior, and pass/fail criteria.
Do not claim general authority from existing duplicate-key tests alone.
### ASSIGNMENT B — DIALOGUE BOX VERTICAL BASELINE
Question:
Why is Utage dialogue text still vertically too high compared with Samurai Heroes even after the FIM/runaway logic is fixed?
Compare exact SH vs current-Utage resources controlling the dialogue plate:
- cockpit1P / relevant owning ARC;
- LSP / PSL / FIM / GSM controller data;
- text node rects, baselines, source rectangles, offsets, line height, anchor/pivot, clipping rects;
- any localisation-only SH differences.
Return:
1. exact owning node/resource;
2. exact field/offset difference;
3. current Utage value;
4. SH value;
5. minimally invasive patch;
6. whether the fix is global or only applies to specific dialogue layouts.
Do NOT hand-wave “font metrics”.
### ASSIGNMENT C — NANBU BATTLE NAMEPLATE
Question:
After official SH cp_name texture synchronization, why can the Nanbu battle plate still show the wrong visible character?
Start from:
rom/eng/id/msg_m019_pl003.arc
current cockpit1P.arc
the exact SH counterparts
the synchronized cp_name donor
Audit:
- Name node resource key;
- UV/source rectangle;
- texture dimensions;
- LSP/PSL coordinates;
- alternate-state selectors;
- any row/column indexing;
- whether the plate samples the wrong cell or an adjacent glyph/label.
Return an evidence table and the smallest corrective patch.
## OPTIONAL SECONDARY WORK
If A-C are blocked, useful static-analysis jobs are:
- find all resource families duplicated byte-identically between title_id and other ARCs and cluster them by likely preload purpose;
- map all resource registration strings in title/title_id/pl_all/gallery/result/tenka and infer collision/resolution behavior;
- diff all SH vs Utage dialogue LSP/FIM controller families and rank differences by direct runtime relevance;
- identify leftover Japanese UI atlas assets that have an exact SH donor and a proven owning LSP, but do not generate or insert replacement art without approval.
## OUTPUT CONTRACT
Return one Markdown report with:
- Executive findings;
- Evidence ledger with PROVEN / STRONGLY SUPPORTED / HYPOTHESIS / DISPROVEN;
- exact file paths;
- hashes/sizes when available;
- exact byte offsets / structure fields for binary claims;
- minimal reproducible runtime test plan;
- “Do not regress” section listing superseded theories;
- any scripts used, included in full and deterministic.
If you cannot prove a claim, say exactly what file/test is missing.
Do not invent owner paths, offsets, struct fields, or runtime behavior.
Do not produce UI art unless explicitly asked.
Do not replace production files unless explicitly asked.
Your handoff must be suitable for direct upload into BASARA Foundry / 06 Agent Handoffs & Audits.
## START
Begin with Assignment A unless the supplied file packet is clearly better suited to B or C.