# BASARA Foundry Core

**Purpose:** preserve the reusable engineering knowledge produced by the Sengoku BASARA 3 Utage English-localisation project so future researchers and AI sessions do not have to rediscover solved facts.

This directory is the public, model-agnostic front door. The active translation build may change; the public core records durable engineering knowledge separately from private/live game binaries.

## What belongs in the public core

Public-safe material includes:

- reverse-engineered format facts and uncertainty bounds;
- parsers, writers and validation tools created by the project;
- algorithms and equations;
- synthetic fixtures and tests;
- hashes and byte-level observations that do not redistribute retail payloads;
- owner/resource topology descriptions;
- runtime experiment design and conclusions;
- disproven hypotheses and known failure modes;
- AI-agent operating rules that make the research reproducible.

Do **not** commit retail ARC/TEX/XET/MSG/EBOOT/audio/video/game-tree payloads or extracted Samurai Heroes/Utage assets.

## Start here

1. Read [PUBLIC_TECHNICAL_CANON.md](PUBLIC_TECHNICAL_CANON.md).
2. Read [PROVEN_FAILURES_AND_GUARDRAILS.md](PROVEN_FAILURES_AND_GUARDRAILS.md).
3. For AI-assisted work, read [AI_PORTABILITY.md](AI_PORTABILITY.md) and the repository's `.agents/skills`.
4. For new research, follow [CONTRIBUTING_RESEARCH.md](CONTRIBUTING_RESEARCH.md).
5. Treat the current repository code/tests as implementation evidence; treat fresh user-supplied game bytes as production authority.

## Separation of concerns

### Public Foundry Core
Reusable research, code, algorithms, schemas, tests, agent skills and failure history.

### Live localisation build
The user's current game files, patched ARCs, EBOOT, retail-derived textures/messages and runtime build state. These are not part of the public core.

### Private convenience layers
Personal ChatGPT memory, connected Drive canon and private plugins may accelerate the maintainer's workflow, but **must never be the only place a durable technical fact exists**.

When a private-session discovery changes future engineering behaviour, promote a public-safe form here.

## Reproducibility principle

A useful research claim should survive the loss of the original conversation.

Prefer records of:

`claim -> evidence -> experiment -> observation -> confidence -> implementation -> regression/test -> superseded assumptions`

That format lets another human or model audit the finding rather than simply trusting an old chat.

## Current public-core milestone

On 2026-09-25 the project formally adopted the rule that BASARA Foundry Core is a public reusable research layer, separate from the private/live patch. The production-contract skill was added so the hard-won safety rules are portable across fresh AI accounts and models.


## Open licensing

BASARA Foundry Core is intentionally open for reuse.

- project-authored code/tools: **MIT**
- project-authored research/docs/agent skills: **CC BY 4.0**
- Capcom/third-party assets: **not licensed by this project**

A portable plugin source package lives in `public-plugin/`.
