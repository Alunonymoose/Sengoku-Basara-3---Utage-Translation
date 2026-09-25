# Sengoku BASARA 3 Utage — English Translation Project

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


## BASARA Foundry Core — public reusable research

This repository is also the public home of **BASARA Foundry Core**: the reusable reverse-engineering knowledge, engineering rules, tests, tools and AI-agent instructions produced while building the Utage English patch.

The goal is that another researcher should **not need to rediscover the same ARC, XET/TEX, ownership, texture, layout and runtime lessons from scratch**.

Start here:

- [Public Core overview](project/Foundry/docs/PUBLIC_CORE.md)
- [Public technical canon](project/Foundry/docs/PUBLIC_TECHNICAL_CANON.md)
- [Proven failures and guardrails](project/Foundry/docs/PROVEN_FAILURES_AND_GUARDRAILS.md)
- [AI portability / fresh-account bootstrap](project/Foundry/docs/AI_PORTABILITY.md)
- [Research contribution rules](project/Foundry/docs/CONTRIBUTING_RESEARCH.md)
- [Reusable agent skills](.agents/skills/README.md)

The public core intentionally contains **research, code, schemas, algorithms, hashes, tests and documentation — not Capcom retail game payloads**. Researchers must supply their own legally obtained game files.

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


## Licence and reuse

The project is intentionally open for reuse:

- project-authored software/tools: **MIT License**
- project-authored documentation/research/agent skills: **CC BY 4.0**
- Capcom/third-party game assets: **not included and not licensed by this repository**

See `LICENSE`, `LICENSE-DOCS.md`, and `NOTICE.md`.

Portable public AI/plugin source: `public-plugin/`.
