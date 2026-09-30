# Sengoku BASARA 3 Utage English Translation Patch (PS3 / BLJM60389)

**English translation patch for Sengoku BASARA 3 Utage on PlayStation 3 (BLJM60389).**  
This project is building a playable English version of **Sengoku BASARA 3 Utage**, including translated menus, UI, textures, dialogue, subtitles, and supporting reverse-engineering/tooling for the PS3 release.

If you searched for **Sengoku BASARA 3 Utage English patch**, **Utage English translation**, **Sengoku Basara 3 Utage PS3 translation**, **BLJM60389 English patch**, or **RPCS3 Utage English patch**, this is the project repository.

## Download / install

The public patch is intended for people who already own and have their own extracted/dumped copy of **Sengoku BASARA 3 Utage (BLJM60389)**.

- [Installation guide](INSTALL.md)
- [v0.1 patch packaging](release/v0.1/README.md)
- GitHub Releases will contain public patch builds when available.

**The repository does not distribute the game, ISO/disc image, or complete retail game files.**

## Project status

This is an active fan-translation and reverse-engineering project. The first public release is being prepared as a **v0.1 preview/test build**.

Current work includes:

- English menu and UI localisation
- translated and rebuilt PS3 textures
- dialogue translation and repair
- cutscene subtitle support
- English resource routing under `nativePS3/rom/eng`
- ARC v8 archive tooling and validation
- MT Framework Lite / TEX/XET reverse engineering
- PS3 and RPCS3 runtime testing
- reproducible patch/install tooling

## Target game

- **Game:** Sengoku BASARA 3 Utage
- **Platform:** PlayStation 3
- **Title ID:** BLJM60389
- **Engine:** MT Framework Lite
- **Reference localisation:** Sengoku BASARA: Samurai Heroes

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

## BASARA Foundry Core

**Current public bootstrap:** `foundry-v0.3-reliability` (state/authority hardening, 2026-09-29). Start with `project/Foundry/docs/PROJECT_CONTROL.md` before domain-specific canon. The older `foundry-v0.1` branch is retained for history and must not be treated as the current bootstrap.

The reusable reverse-engineering knowledge, tools, agent skills, technical canon and proven-failure history are maintained publicly on the **`foundry-v0.3-reliability`** branch.

Start with:

- [BASARA Foundry Core](https://github.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/blob/foundry-v0.3-reliability/project/Foundry/docs/PUBLIC_CORE.md)
- [Public technical canon](https://github.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/blob/foundry-v0.3-reliability/project/Foundry/docs/PUBLIC_TECHNICAL_CANON.md)
- [AI portability / fresh-account bootstrap](https://github.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/blob/foundry-v0.3-reliability/project/Foundry/docs/AI_PORTABILITY.md)
- [Reusable agent skills](https://github.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation/tree/foundry-v0.3-reliability/.agents/skills)

The intent is that future researchers should not need access to the maintainer's private ChatGPT history, memory, Drive or plugin to reuse the project's solved engineering.

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

The repository is intended to preserve the project's original research, tooling and documentation rather than redistribute Capcom game content.

## Licence and reuse

This project is intentionally open for reuse:

- project-authored software/tools: **MIT License**
- project-authored documentation/research/agent skills: **CC BY 4.0**
- Capcom/third-party game assets: **not included and not licensed by this repository**

See `LICENSE`, `LICENSE-DOCS.md`, and `NOTICE.md`.

The reusable BASARA Foundry Core and portable AI/plugin source are maintained on the `foundry-v0.3-reliability` branch.
