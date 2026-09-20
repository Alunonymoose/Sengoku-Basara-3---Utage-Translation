# SENGOKU BASARA 3 UTAGE — 24-HOUR CROSS-CHAT CHECKPOINT
Date: 2026-09-20
Scope: material project knowledge established across chats on 2026-09-19 → 2026-09-20.
Purpose: durable recovery point. Newer runtime evidence supersedes older guesses when they conflict.
## 1. CURRENT LIVE / PRELOAD ARCHITECTURE — VERIFIED
- The patched EBOOT loads ENG title.arc and then ENG title_id.arc before select/c_common.arc.
- rom/eng/title_id.arc is the effective English resident preload / current canonical source for the synchronized charasele_02 character-name family.
- charasele_02_000..029 is synchronized 210/210 across seven owner classes: title_id, title, common/pl_face/pl_all, per-player pl_face, gallery, result, and tenka/get_pl.
- common/pl_face/pl_all.arc is the synchronized stock-equivalent central mirror of the title_id canonical set.
- Live Drive UPN tree was reconciled in place on 2026-09-20: 137 existing files updated with Drive IDs preserved.
- Tenka mission enemy-name corruption in tenka_m016..029 was repaired using official Samurai Heroes donors from the same mission index. Do not map tenka_pl player index as mission index.
Canonical Drive evidence already exists under:
00 Canon & Current State / 00 ACTIVE MASTER — READ BEFORE PATCHING / 2026-09-20 — VERIFIED LIVE SYNC — CHARASELE02 + TENKA NAMES
## 2. TITLE_ID RESIDENT RESOURCE PROOF — VERIFIED, SCOPE-LIMITED
Generic Unification Character Select was runtime-tested with:
- physical rom/eng/common/pl_face disabled;
- pl003.arc absent;
- title_id internal rArchive alias for rom\eng\common\pl_face\pl003 changed to zz003;
- A/B tests neutralizing charasele_02_003 in title.arc or title_id.arc independently;
- a full-family test neutralizing 86 pl_all-equivalent registrations in title.arc while normal title_id remained present.
Observed result:
- Ieyasu and Hisahide Matsunaga still rendered correctly.
- RPCS3 logs showed no physical common/pl_face accesses for the tested screen.
- Either resident title.arc or title_id.arc could satisfy an already-loaded same-name charasele_02 resource key.
- With title.arc duplicates neutralized and physical common/pl_face absent, normal title_id alone supplied the tested pl_all-equivalent resources.
- Current pl_all.arc contains 112 entries; all 112 are byte-identical in current title_id.arc; 86 of those are also duplicated in title.arc.
Interpretation:
- PROVEN for generic Unification Character Select: title_id can act as sole resident provider for the tested existing pl_all-equivalent family.
- NOT YET PROVEN for every screen, every owner class, or arbitrary newly-added resource families.
- Next decisive architecture test should use a resource family not already resident in title/title_id, move it into title_id, neutralize the original local owner, and test a known consumer.
## 3. CHARACTER NAME SYSTEMS — DO NOT CONFLATE THEM
Two separate systems exist:
- cp_name_pl_000..029 is deterministically mapped in select/c_story.arc and remains a real texture family, including stacked 256x128 special slots 005/011/013/016 with lower alternate states.
- However, c_story cp_name_pl was ruled out as the visible owner for the Character Select / Gallery nameplate problem being debugged on 2026-09-19.
- friend_003.arc and vs_cockpit.arc were also ruled out for that visible owner path.
- The visible generic Character Select charasele_02 family is now proven resident via title/title_id preload as above.
- Do not merge cp_name_pl ownership conclusions with charasele_02 conclusions.
Additional MSG-side cp_name work:
- ROOT-READY artifact UTAGE_MSG_NPC_CP_NAME_SYNC_ROOT_READY.zip repaired 374 cp_name_pl XET instances across 356 mission ARCs, including the Nanbu 100 donor replicated to 30 copies.
- If the Nanbu battle plate still displays an incorrect single letter after official SH texture synchronization, the next owner to inspect is cockpit1P Name-node / UV sampling rather than assuming the MSG texture itself is wrong.
## 4. MSG / GSM / FIM SYSTEM — CURRENT AUTHORITY
Major supersessions from the 2026-09-20 MSG-ASCII audit:
- The old “m005 has a 138-primary-row deficit” theory is DISPROVEN.
- The September 14 FIM contract is the current runaway-dialogue authority: production regeneration must rebuild FIM column 0 and column1.high16 consistently.
- Recovered production grammar state includes FC17 = 3 and FF91 = 0.
- The separator fix was hardware/runtime proven across 1,287 archives / 1,590 slots.
- A 1,379-archive undo/recovery ledger exists.
- m999’s 30 archives remain intentionally skipped/untranslated in that recovered production pass.
- old msg_edit.py is superseded/quarantined and must not be treated as current production authority.
- SB3 JPN ↔ Samurai Heroes comparison yielded 608 localization pairs, but direct SH GSM transplant / “global SH ASCII solves mission dialogue” is not the correct general model. Pristine Utage structure remains authoritative and SH is a donor/contract reference, not a blind replacement source.
- EVS/EVS2 restoration is not release-critical unless a live surface proves a need.
Specific live fixture:
- rom/eng/id/msg_m019_pl003.arc / msg\m019_03\jpn\m019_03 contains the Nanbu broken dialogue-plate case around GSM row 501; a relevant speaker/control difference was observed between current Utage and SH (current 0002 vs SH 0001 in the compared control sequence).
- Runtime visual parity is still not complete: dialogue-box text is visibly too close to the top compared with Samurai Heroes. Treat the FIM/runaway fix as solved logic, not proof that every LSP/box baseline matches SH.
Canonical authority:
00 Canon & Current State / 00 MSG-ASCII SYSTEM AUDIT — SB3 JPN → SAMURAI HEROES → UTAGE — 2026-09-20
GitHub recovery tools:
project/dialogue_tools/fim_contract_recovery_2026-09-20/
## 5. WESTERN FONT / ASCII ARCHITECTURE — HYBRID CONTRACT, NOT GLOBAL SWAP
Current model:
- Use Utage’s fixed eng/jpn loaders and preserve mission/local structure.
- Use Samurai Heroes TNF / CSA / ASCII atlases and localization-side LSP/FIM deltas where the specific bundle contract is verified.
- Do not copy only atlas XETs and do not globally replace every Utage text resource with SH.
Verified / current:
- Gallery’s SH TNF/atlas contract is runtime visually verified and should be frozen as a known-good family.
- Verified Gallery V1 gallery.arc: 771,643 bytes; SHA-256 02c145fabae208c638576b8e116103c52fe4d47db4b2e334139641e8ec91b02e.
- The V1 Western-font pass restored exact SH ASCII TNF/atlas 00/01 where appropriate and applied the relevant Tenka top_00 Name/Army localization delta while preserving Utage extras.
- 78/78 unrelated Tenka members were preserved in that pass.
- Tenka remains separately unverified visually; do not assume Gallery verification proves Tenka.
- SH tenka_id.arc does not simply provide local id_tenka_00/01 replacements. The localized presentation depends on SH GSM/FIM/Western LSPs/textures plus global ASCII resources.
ROOT-READY/reference artifacts:
- UTAGE_SH_WESTERN_FONT_CONTRACT_PASS_V1_ROOT_READY.zip
- UTAGE_SH_WESTERN_FONT_CONTRACT_PASS_V1_MATRIX.csv
## 6. GUIDE PANEL DONOR POLICY — CURRENT MAPPING
For pause/system guide-panel work:
- Direct exact SH transplant set: sys_000, sys_002, sys_003, sys_006.
- Pristine-JPN guided / no-direct-SH set: sys_001, sys_004, sys_005, sys_007, sys_008, sys_009, sys_010, sys_011, sys_012.
- Source mapping is rom/jpn/pause/sys_NNN.arc → system_NNN_ID_HQ.
- Do not turn “no exact SH donor” into a random global donor swap.
## 7. LOCAL GOODS — OWNER SOLVED, ART NOT APPROVED
- Local Goods atlas asset is id\texture\jpn\tenka\tenka_012_ID_HQ.
- It is duplicated in tenka_id.arc and result_id.arc.
- Texture: 512x512, XET 0x97 / BC3 0x2A.
- Relevant lower-right atlas target is approximately x384–508, y279–355.
- The proposed LOCAL / GOODS replacement generated on 2026-09-20 was rejected and must not be promoted or inserted.
- Future work must follow the approval-first texture transaction and patch the actual XET/ARC only after approved artwork and layout preview.
## 8. ROULETTE / COCKPIT OWNER REFERENCE
- Roulette asset path: nativePS3\rom\eng\id\cockpit1P.arc
- Member: id\texture\jpn\roulette\roulette_000_ID_HQ
- Pristine JPN counterpart is in nativePS3\rom\jpn\id\cockpit1P.arc.
- Existing generated Roulette candidates from 2026-09-20 are not automatically approved; preserve approval-first rule.
## 9. TITLE SCREEN — CLOSED BASELINE, DO NOT REOPEN
The 2026-09-18 title_004 Sengoku clean-edge repair remains CLOSED / runtime visually verified / user-approved.
Do not regress to older v3/v5/v6 experiments or reopen solved 0x2A channel semantics.
Accepted title facts:
- PS3 0x2A Kuriimu2 packing: G=coverage, A=Y, R=Cr, B=Cb.
- Global neutral chroma is a failed strategy.
- Successful clean-edge repair preserves antialiased alpha and preconditions transparent RGB with Sengoku blue before 0x2A conversion / BC3 encode.
- Only certified blocks in the 368x176 HQ logo_sengoku source region are grafted.
- title_005 and title_006 were untouched for the accepted Sengoku-only fix.
## 10. CURRENT FAILURE / SUPERSESSION LEDGER
Do not revive these as current truth:
- “copy SH atlas only” as a general font fix — rejected.
- “global SH ASCII transplant fixes all dialogue” — disproven.
- “m005 138-row deficit is the runaway root cause” — disproven.
- old msg_edit.py as production message tooling — superseded.
- c_story cp_name_pl as owner of the visible generic Character Select/Gallery nameplate issue — superseded for that screen.
- friend_003.arc or vs_cockpit.arc as that visible nameplate owner — ruled out.
- arbitrary whole-archive SH Tenka replacement — unsafe.
- rejected Local Goods artwork — do not patch.
- any diagnostic build that neutralized aliases/registrations is test evidence, not a live production baseline.
## 11. LIVE-SAFETY / DISABLED-FOLDER DISTINCTION
- The proven runtime test disabled physical rom/eng/common/pl_face, NOT the entire rom/eng/id tree.
- The live id tree itself was previously assessed as correct for the Nanbu case; that plate issue traced into parallel rom/eng/msg mission archives / cockpit presentation rather than requiring the whole id directory to remain disabled.
- Keep diagnostics that rename/neutralize title/title_id registrations separate from production.
- Preserve the normal live title.arc and title_id.arc after tests unless a specific verified production change is being promoted.
## 12. STANDING PRODUCTION RULES RECONFIRMED
- Current/live ARC first; hash-confirm preservation base.
- Texture transaction: ARC → owner → XET/TEX → LSP/PSL → decode → artwork → exact atlas candidate → layout preview → STOP FOR APPROVAL → encode/graft → rebuild ARC → verify unaffected resources → ROOT-READY ZIP.
- Exact compatible SH donor first; otherwise create new English art from the actual source texture.
- Do not infer “Japanese visual” from an internal \jpn\ path alone.
- Every material discovery, failed theory, approved patch, runtime result, donor mapping, and supersession goes back into BASARA Foundry.
- Final patch delivery should be a single ROOT-READY ZIP with correct game-root structure unless explicitly requested otherwise.
END CHECKPOINT.