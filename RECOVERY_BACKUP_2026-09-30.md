# Recovery Backup — Pipelines / Cutscenes / Textures / Dialogue — 2026-09-30

This branch is a dated preservation snapshot created from `foundry-v0.3-reliability`.

Purpose: make sure the project's reusable engineering survives loss of local E: state or private chat context.

## Coverage

### General pipelines
Preserved directly in this branch:
- `.github/workflows/`
- `project/Alrummi3/`
- `project/_codex_select_menu/`
- `project/_codex_tenka_v6/`
- `project/pipeline/`
- `project/tools/`
- `project/Foundry/`
- `project/media_tools/`

### Texture engineering
Preserved directly:
- `project/texture_tools/`
- `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/`
- `.agents/skills/basara-utage-texture-engineering/`
- `public-plugin/skills/basara-utage-texture-engineering/`
- older/result/quest texture build scripts under `project/_codex_tenka_v6/` and `project/_codex_select_menu/`

Current recovery summary:
- `project/recovery/2026-09-30/TEXTURE_PIPELINE_RECOVERY.md`

### Dialogue / GSM / FIM
Preserved directly:
- `project/dialogue_tools/fim_contract_recovery_2026-09-20/`
- `project/pipeline/dialogue_integrity_guard.py`
- `project/FIX_dialogue_desync.ps1`
- `project/UNDO_dialogue_desync.ps1`
- `project/forensics/COLLECT_dialogue_runaway_forensics.ps1`
- `project/forensics/DEEPSEEK_ASSIGNMENT_DIALOGUE_RUNAWAY_ROUTE_DIVERGENCE.md`

Current recovery summary:
- `project/recovery/2026-09-30/DIALOGUE_PIPELINE_RECOVERY.md`

### Cutscenes / subtitles / PAM
GitHub already preserves:
- `project/media_tools/pamftool_utage_patch.py`
- `.github/workflows/build-utage-pamftool.yml`
- Foundry public canon and runtime/research architecture around MT Framework resources.

The newest native-EVS/PAM authoring scripts themselves were found referenced in Drive canon but were not found as standalone GitHub/Drive source files during this 2026-09-30 recovery audit. Their algorithms, filenames, states, hashes and recovery locations are therefore explicitly preserved in:
- `project/recovery/2026-09-30/CUTSCENE_SUBTITLE_PIPELINE_RECOVERY.md`

This is a known remaining durability gap, not silently treated as complete.

## Authority warning

This branch is a recovery snapshot, not current production authority.
Fresh exact live bytes still outrank this branch for mutation decisions.

No retail game payloads are intentionally added here.
