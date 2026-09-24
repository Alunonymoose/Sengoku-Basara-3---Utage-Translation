# BASARA Foundry v0.2 — Reproducible Localisation Architecture

## Problem being solved

The project has strong low-level tooling but repeatedly loses time because independent handoffs, old ARC copies, duplicate providers, historical screenshots, and agent memory can all look authoritative. A correct tool can therefore be run against the wrong bytes, or a completed family can remain listed as open.

v0.2 changes the unit of truth from document/file name to content-addressed build state.

## Authority model

1. Current live bytes — exact PS3_GAME snapshot and file/resource hashes.
2. Observed runtime evidence — RPCS3 logs, screenshots/video, RSX evidence, bound to the exact snapshot.
3. Approved production recipe — exact source snapshot, provider hashes, candidate hash, encoder/mask and expected outputs.
4. Canonical terminology/specification — reusable semantic rules, independent of one live build.
5. Handoffs and research prose — context/history only. They may propose facts but cannot override contradictory live/runtime evidence.

## Build graph

    LIVE PS3_GAME
        -> SNAPSHOT (tree SHA-256)
        -> FILE + ARC/RESOURCE INDEX
        -> PROVIDER GRAPH <- optional RPCS3 LOAD LOG
        -> RESOURCE QUERY
        -> DONOR / TERMINOLOGY
        -> PATCH RECIPE
        -> candidate SHA-256
        -> USER APPROVAL
        -> VERIFIED ENCODER / GRAFT
        -> STRUCTURAL VERIFY
        -> CANDIDATE BUILD
        -> RPCS3 RUNTIME EVIDENCE
        -> GOLDEN VISUAL CHECK
        -> RELEASE DELTA

## Resource identity

Runtime identity is never inferred from filename similarity. The key is (type_hash, ASCII-lowercased exact internal path). Locale-equivalent or visually similar paths are analysis relationships only and must not be treated as runtime identity.

## Runtime precedence

Static folder order is not sufficient. If an RPCS3 log is supplied, the existing Resource Ownership Analyzer derives observed ARC-open order. v0.2 stores the resulting rank per ARC and exposes an observed earliest provider in resource queries. No log means provider precedence is UNKNOWN, not guessed.

## Patch transaction contract

A production patch must eventually satisfy all of these gates:

1. Source snapshot still matches live bytes.
2. Every provider expected by the recipe still has the recorded ARC/resource hash.
3. Candidate artwork/text hash equals the approved candidate hash.
4. Encoder/tool version is explicit.
5. Edit mask or exact member replacement scope is explicit.
6. Rebuilt resource round-trips to expected decoded bytes.
7. Untouched ARC members remain byte-identical in stored form where the writer contract requires it.
8. Duplicate providers required by the ownership graph are synchronized.
9. Output ARC hashes are recorded.
10. Runtime evidence is bound to the resulting candidate tree hash.

No gate may be satisfied by a prose statement alone.

## External engineering patterns adopted

- SLSA-style provenance: exact inputs, subjects and build provenance.
- DVC-style stage graph/run cache: unchanged hashed inputs should not trigger rework; large private history can use content-addressed remote storage.
- Kaitai-style formal binary specifications as independent parser/visualisation fixtures.
- Property testing: round-trip and preservation properties for ARC/GSM/FIM/XET tooling.
- Git worktrees/branches: concurrent agents work from immutable snapshot IDs and isolated branches.
- RPCS3 RSX capture / graphics debugging: runtime draw evidence for stubborn visual ownership.
- Golden-image regression: canonical screenshots with masks for dynamic regions.
- Hash-checked binary deltas for eventual public release.

## Repository authority cleanup

Target stable entry points:

    project/orchestration/   machine truth, recipes, snapshot queries
    project/Foundry/         GUI and domain/game adapters
    project/tools/           production tools behind stable contracts
    project/runtime/         runtime acceptance templates/evidence
    project/terminology/     canonical English terminology
    project/spec/            formal binary specs/fixtures (future)
    archive/                 historical one-off work, never imported by production

Dated tool directories remain temporarily for compatibility but should stop becoming new public entry points. Git history supplies versions; production imports should eventually use stable module names.

## Agent protocol

Every AI task should start from an explicit snapshot_id, resource identity/runtime row, and allowed action (research, candidate, patch, runtime-analysis). An agent may not promote its own candidate. If the snapshot changes, patch execution fails closed and must be rebased.

## Failure modes this directly prevents

- asking for a folder that does not exist in Samurai Heroes;
- treating a jpn internal namespace as proof of visible Japanese art;
- calling byte-identical JPN/ENG textures untranslated when they are language-neutral;
- rebuilding completed waza families from stale backlog text;
- patching a wrongly attributed texture because an old note said it owned a glyph;
- overwriting newer live ARCs with historical Drive copies;
- treating regenerated artwork as still approved after its pixels changed;
- claiming runtime success from structural verification alone.

## Definition of v0.2 done

v0.2 is done when a clean machine can snapshot the live build, query any resource/provider deterministically, bind runtime load evidence, create/validate a hash-bound recipe, execute it through verified writers, bind structural/runtime evidence to the candidate tree hash, and reproduce the same final patch from the same inputs.
