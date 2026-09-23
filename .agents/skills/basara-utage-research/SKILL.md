> **2026-09-23 RESEARCH SUPERSESSION — READ FIRST**
>
> Two historical assumptions are now explicitly falsified: (1) 0x2A is not a bespoke raw-YCbCr surface; the old appearance came from decoding BC block data with half dimensions, and (2) rom/jpn is not reliably pristine Japanese; it contains English/shared assets, so hash equality is classification evidence only, never semantic proof. Research should start from the solved XET contract, Resource Ownership Analyzer, Donor Matcher V5.1 and the Release Completion Gate.
>

---
name: basara-utage-research
description: Evidence-driven reverse-engineering and research workflow for Sengoku BASARA 3 Utage and BASARA Foundry. Use for unknown formats/fields, public-source comparison, forensic audits, cross-game evidence, hypothesis testing, external-agent handoffs, and canon updates.
---

# BASARA Utage Research

Use this skill when the task is to learn something that the production pipeline does not yet know with sufficient confidence.

The user's explicit instructions take precedence over this skill. Research should accelerate engineering, not become an excuse to defer a concrete task that can already be completed safely.

## Core rule

Do not start from broad generic MT Framework lore when the project already has Utage evidence.

Recover the BASARA Foundry source of truth first, then identify the exact unresolved claim.

## Evidence labels

Every consequential technical conclusion should be tagged mentally or explicitly as one of:

- `PROVEN BY REAL UTAGE RUNTIME`
- `PROVEN BY REAL UTAGE FIXTURE`
- `PROVEN BY SUPPLIED/CURRENT CODE`
- `PROVEN EXTERNALLY`
- `STRONGLY SUPPORTED`
- `HYPOTHESIS`
- `DISPROVEN`

Do not collapse these categories.

A synthetic test can prove internal consistency. It cannot, by itself, prove Capcom's real binary semantics.

## Research order

Prefer evidence in this order:

1. exact real Utage runtime observation tied to a known build/hash
2. exact real Utage binary fixture
3. current Foundry code plus deterministic fixture regression
4. public PS3 MT Framework source/tool matching the same platform/code path
5. Samurai Heroes/Sengoku BASARA 4/Sumeragi or another closely related Capcom title
6. generic MT Framework documentation
7. community posts/scripts
8. hypothesis

Cross-game evidence is useful, but never silently promote it over Utage-specific evidence.

## Before researching

Answer these questions:

- What exact claim is unresolved?
- What existing project evidence already constrains it?
- What would falsify the current hypothesis?
- What smallest fixture/test could settle it?
- Is the result needed for read support, write support, or runtime certification?

Avoid broad rescans when a narrow known-answer test can answer the question.

## Public-source research rules

When using public repositories/tools:

- prefer source code over prose claims
- identify platform and game/version
- distinguish parser behavior from writer behavior
- identify endian assumptions
- identify whether compressed data is handled as pixels, BC blocks, tiled blocks, or opaque bytes
- inspect actual encode paths, not only format-name tables
- record the exact function/file that supports the claim

Do not call a report a faithful port if it substitutes a different codec/algorithm without saying so.

## BASARA-specific cautions

### ARC

Do not reuse generic speculative entry layouts. Current certified Utage ARC v8 evidence uses the PS3 big-endian `\0CRA` form and 80-byte table entries.

Compression behavior must be fixture-backed. A size inequality alone is not universal proof of codec semantics.

### TEX/XET

`\0XET` is the PS3 MT Framework texture signature, not Exient XGS.

Treat v0x97/header field interpretations as fixture/code claims and test them against real Utage samples.

Do not reintroduce the old blanket PS3 8x4/Morton swizzle theory unless a real fixture requires it.

### 0x2B / RBxG

Research must preserve the distinction between stored BC3 channels and artist-facing representation.

Known project transform:

`base = (A,A,A,G)`

`mask = (R,B,0,255)`

`stored = (mask.R, base.A, mask.G, base.G)`

Any external claim that reduces this to a simple G/A swap is incomplete unless it explains what happens to stored R/B.

### PSL/LSP

Layout field semantics are fixture-specific until proven across multiple real assets.

A parser finding coordinates/strings does not prove a safe writer or universal field meaning.

### Cross-game assets

Samurai Heroes and Sumeragi are references, not donors by default.

Never infer that identical resource names imply identical controller ownership, channel semantics, UV expectations, or runtime routing.

## External-agent handoff discipline

When using DeepSeek, Claude, or another model:

- give it the exact unresolved question
- give it the current known facts and disproven assumptions
- include the real code/fixture excerpts it needs
- ask it to falsify, not merely agree
- require exact source/function references
- require unknowns to remain unknown
- do not let it redesign the whole pipeline unless the current architecture is actually disproven

After receiving an external report, independently audit its strongest claims against current source/fixtures before promoting them to canon.

## Forensic review checklist

For each claimed defect or discovery, trace:

- file/class/function
- exact code path
- realistic Utage failure scenario
- what bytes/pixels/runtime state change incorrectly
- why current verification would miss it
- minimal repair
- regression needed
- evidence level

Prefer a small adversarial fixture over a long speculative essay.

## Canon update rule

A discovery belongs in BASARA Foundry canon when it materially changes how future agents should engineer the patch.

When promoted:

1. update current code/tests if applicable
2. update the relevant skill if workflow behavior changes
3. update Drive technical canon/checkpoint
4. record provenance: source/fixture, date, branch/commit/test when useful
5. record any superseded rule explicitly so future agents do not revive it

## Proven failures that should remain visible

Keep these historical corrections easy to recover:

- `\0XET` is MT Framework TEX; the Exient/XGS interpretation was wrong
- speculative 16-byte ARC entries were wrong for the certified Utage v8 path
- ARC v8 entries are 80 bytes in current certified code
- PS3 structures in the certified path are big-endian
- generic whole-pixel Morton/swizzle code was not proven for the linear UI fixtures
- pristine-payload-as-default incremental base is unsafe because it can revert existing English art
- ordinary artist-facing RGBA for 0x2B is unsafe/incomplete
- matching-name cross-game transplantation is not an ownership proof

## Research stop condition

Stop researching and return to engineering when the unresolved claim has enough evidence to support a deterministic fail-open or fail-closed implementation plus an appropriate regression.

Do not keep expanding scope once the blocker is settled.
