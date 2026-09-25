# Sengoku BASARA 3 Utage â€” English Translation Project

English translation and reverse-engineering project for
**Sengoku BASARA 3 Utage** on PlayStation 3.

## Repository purpose

This repository preserves project-created material including:

- reverse-engineering research
- translation architecture notes
- scripts and utilities
- ARC/resource mappings
- manifests
- hashes
- patch history
- test results
- technical handover documentation
- reproducibility information

## Copyrighted game data

Original or modified retail game files are intentionally excluded.

This includes:

- ARC archives
- EBOOT / SELF / ELF binaries
- retail textures
- retail message files
- audio
- video
- extracted PS3 game trees
- complete Samurai Heroes assets
- complete Utage assets
- disc images

The repository is intended to preserve the project's original research,
tooling and documentation rather than redistribute Capcom game content.

## Target game

Sengoku BASARA 3 Utage  
PlayStation 3  
BLJM60389

## Localisation reference

Sengoku BASARA: Samurai Heroes is used as an English localisation and
technical reference where appropriate.

## Current engineering front door

Development of the reproducible project-state layer is on `foundry-v0.2-orchestration` pending review. The command-line front door is `project/foundry.ps1`; it snapshots the exact live `PS3_GAME` tree into a content-addressed SQLite index and binds ownership, patch recipes, approvals, runtime evidence, and visual regression to that snapshot.

Historical handoffs and dated work directories are context only; they do not outrank a verified current-live snapshot or runtime evidence.
