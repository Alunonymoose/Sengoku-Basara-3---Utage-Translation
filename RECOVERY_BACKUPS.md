# Recovery Backups

A dated preservation snapshot of the project's reusable engineering was created on:

**Branch:** `backup-pipelines-2026-09-30`

It was forked from `foundry-v0.3-reliability` and preserves the current GitHub-resident pipeline/tooling state for:

- general patch/build pipelines
- textures / XET / BC tooling
- dialogue / GSM / FIM tooling
- cutscene / subtitle / PAM research

Recovery index on that branch:

`RECOVERY_BACKUP_2026-09-30.md`

Domain recovery notes:

- `project/recovery/2026-09-30/TEXTURE_PIPELINE_RECOVERY.md`
- `project/recovery/2026-09-30/DIALOGUE_PIPELINE_RECOVERY.md`
- `project/recovery/2026-09-30/CUTSCENE_SUBTITLE_PIPELINE_RECOVERY.md`

## Known remaining gap

The newest native-EVS subtitle authoring/install scripts are referenced in Drive/current canon but were not found as standalone source files in GitHub or Drive search during the 2026-09-30 recovery pass. Their algorithms, filenames, state and recovery locations are preserved in the cutscene recovery note, but the exact script bytes still need to be copied from local E: when access is restored.

This file exists so that the recovery branch and the remaining durability gap are visible from `main`.
