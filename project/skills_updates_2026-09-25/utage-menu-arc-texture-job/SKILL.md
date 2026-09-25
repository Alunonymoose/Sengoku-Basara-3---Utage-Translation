---
name: "utage-menu-arc-texture-job"
description: "Start or resume the Sengoku BASARA 3 Utage Versus menu.arc texture quality pass in E:\\Utage Patching New — read CLAUDE.md and the job brief, load the basara skills, work family-by-family, stop at candidate approval."
---

# Utage — Versus menu.arc texture quality job (launcher)

This skill is the kickoff for the job defined on disk. It does not replace the project files. **The files in `E:\Utage Patching New` are the authority**: read them fresh every run. If they differ from this skill, follow the files and say what changed.

Equivalent Claude Code kickoff (open `E:\Utage Patching New` as the project, then say):
> Read CLAUDE.md and CLAUDE_MENU_ARC_JOB.md in full, load the relevant .claude skills, and execute the menu.arc texture quality job. Work family-by-family and stop custom art at the exact candidate approval gate.

## 1. Open the project

- Claude Code: the working directory is `E:\Utage Patching New`.
- Cowork: make sure `E:\Utage Patching New` is a connected folder (request access to that one folder if it isn't). Use the shell on the laptop when one is available. If there isn't one, stage only the files each step needs into the cloud workspace and do the work there.

## 2. Read in full before anything else (no skimming, no working from memory)

1. `CLAUDE.md`: production gate, authority order, state chain, texture hard gate
2. `CLAUDE_MENU_ARC_JOB.md`: goal, live target, startup order, first report, family loop
3. `.claude/skills/basara-production/SKILL.md`
4. `.claude/skills/basara-texture-engineering/SKILL.md`
5. `.claude/skills/basara-arc-engineering/SKILL.md`
6. `.claude/skills/basara-qa/SKILL.md` (this job starts as an audit)

Also list `.claude/skills/` in case new skills were added. Load any that apply.

## 3. Targets and known-good tools

- Live ENG (mutation authority): `PS3_GAME\USRDIR\nativePS3\rom\eng\versus\menu.arc`
- **Progress:**
  - 2026-09-25: member 58 (`kessen_001_ID_HQ`), all 8 label slots. v1/v2 (`bdbe4e7c…`) were written with xetenc and rendered wrong (navy plate). **v3** re-encoded with standard BC order + YCbCr: live sha `ee9b0da1…`, backup `_MENU58_LABELS_V3_BACKUP_2026-09-25\`, records + `swapdec.py`/`v3.py` in `_MENU_ARC_QUALITY_2026-09-25\kessen_001\v3\`. Cold boot to confirm.
  - Member 58's slots are proven by `kessen_rule` PSL (nodes 6/7/77/80/83/85/88/92).
  - Nodes 72/95 (`Cursol`/`Cursol_s`) are selection cursors. Decoded correctly (standard order + YCbCr) they are white frames, empty inside; the earlier "cyan mask material" was an artefact of the swapped reading.
- JPN reference: `PS3_GAME\USRDIR\nativePS3\rom\jpn\versus\menu.arc`
- Re-hash live ENG first. If the hash differs from the one in the job brief, the new bytes win. Update the baseline and say so.
- Loose `kessen_*.tex/.lsp` files sitting next to `menu.arc` are evidence only. Prove what gets loaded before you trust any of them over the ARC member.
- Tools to reuse (don't rewrite them from scratch):
  - **Texture codec: `basara tex …` / `basara.xet` (GitHub `project/basara`, `pip install -e project/basara`).** `xetenc.py`/`xet3.py` in `_codex_tenka_v6\xetenc_RECOVERED_2026-09-24\` are QUARANTINED: never write with them.
  - `_codex_tenka_v6\msg_tools_2026-09-24\arc_tools.py` (parse/rebuild)
  - `_codex_tenka_v6\UTAGE_PIPELINE_MANIFEST.json` (census of where each key lives)
- Project facts to honour:
  - `rom/jpn` is not reliably pristine. It holds some English/shared assets, so a byte match against JPN never proves a texture is Japanese. Render and read it.
  - 0x2A colour semantics are RESOLVED: standard BC order + Kuriimu2 YCbCr (utage-texture-pipeline §2). Work in display RGBA from `decode_display()`.
  - BC edits must respect 4x4 blocks.
  - Co-resident duplicate keys need provider/equivalence proof before any lockstep edit.
  - The magenta/green `cp_name_pl` splash nameplates are approved art, not defects.

## 4. Execute: this order, no image generation before step 6

1. Parse live ENG + JPN ARCs. Inventory and decode every XET/TEX member.
2. Compare ENG against real JPN and any proven Samurai Heroes donor (`E:\SAMURAI HEROES`).
3. Prove consumption from LSP/PSL layouts (e.g. `kessen_rule`, `kessen_sele`). Japanese in an unused or support atlas area is not a target.
4. Classify each texture as `ACCEPTABLE | UNTRANSLATED | BROKEN | LOW-QUALITY | VERIFY` and rank by visible value.
5. **First report** (send to the user, then keep going without waiting): live SHA-256 + member count · classification summary · highest-value family · first member/path · consumer/layout evidence · exact edit masks · planned candidate set. Re-prove the member 58 masks `(0,0)-(512,64)`, `(0,64)-(512,128)` against current bytes before you use them.
6. **Family loop.** Do one family at a time: audit → usage proof → frozen masks → isolated art only → deterministic composite onto a copy of the real decoded live sheet → out-of-mask identity check → `candidate_manifest.json` → deterministic comparison board (real current + real reference + exact candidate) → **STOP**.

Save the working outputs in a dated job folder, e.g. `E:\Utage Patching New\_MENU_ARC_QUALITY_<YYYY-MM-DD>\<family>\`. Never put working outputs in `rom\`; only the verified install touches it.

## 5. The approval gate (hard stop)

At the gate, present for each candidate:
- the comparison board
- the manifest summary: source hash, member, dimensions/format, masks, candidate hash, `unchanged_outside_mask: true`, `approval_required: true`, `arc_patched: false`

Then stop. Before approval:
- no encoding
- no ARC rebuild
- no live write
- no advancing a state label past `CANDIDATE`

Reject weak candidates yourself before you show them.

**After approval:** the approved pixels are frozen. Encode with `basara tex arc-graft`. Rebuild only the budgeted members. Reparse the finished ARC, re-extract, decode the stored texture and compare it to the approved PNG. Verify protected members are byte-identical. Show the final decode for a second approval.

**USER HARD RULE:** no ROOT-READY ZIPs. Install directly on live E:, but only after a hash-verified dated backup of the ARC (`_<TOPIC>_BACKUP_<date>\`). Follow the full protocol in utage-session-start §6: backup, mtime-guarded write, re-stage, re-verify, `INSTALL_RECORD.json`.

Report only the evidence level actually reached: `HYPOTHESIS | STRUCTURALLY VERIFIED | VISUALLY VERIFIED | RUNTIME OBSERVED | RUNTIME PROVEN`. Cold boot in RPCS3 is the final acceptance gate.

## 6. Resuming

If a `_MENU_ARC_QUALITY_*` folder already exists:
1. Read its manifests.
2. Check which families are awaiting approval and which were approved in chat.
3. Continue from there.

Never regenerate a candidate that is already awaiting approval unless the user reopens it.

## Behaviour

- Work autonomously up to each approval gate. Don't send the user off to preprocess or export anything you can do yourself.
- When a fact is unresolved, fail closed on that exact fact. Don't invent a proxy for it.
- Keep Drive docs as backup/documentation only. Live E: bytes decide what is installed.