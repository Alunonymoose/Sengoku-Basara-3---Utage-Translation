# Contributing Reverse-Engineering Findings

The aim is not merely to collect conclusions; it is to make them auditable and reusable.

## A good finding contains

- **Claim:** the narrow technical statement being tested.
- **Scope:** exact game/platform/resource family/fixture.
- **Prior state:** what was believed before.
- **Evidence:** file hash, runtime screenshot/capture, code path, public-source function, synthetic fixture, etc.
- **Experiment:** smallest test that distinguishes competing explanations.
- **Observation:** what actually happened.
- **Confidence:** hypothesis / structurally verified / visually verified / runtime observed / runtime proven.
- **Implementation impact:** parser/writer/workflow change.
- **Regression:** test or repeatable check that prevents reintroduction.
- **Supersession:** older rule explicitly marked wrong or narrower when appropriate.

## Public-safety rule

Do not attach or commit copyrighted retail payloads.

Prefer:

- SHA-256 hashes;
- member/path names where needed for reproducibility;
- structural metadata;
- short hex/field descriptions when necessary to explain a format;
- project-authored code;
- synthetic fixtures;
- equations/algorithms;
- runtime observations;
- screenshots only when legally appropriate for project documentation.

## Evidence discipline

Evidence weight depends on the claim. For game-specific runtime semantics, a real Utage runtime result tied to a known build outweighs generic MT Framework documentation. For implementation behaviour, current source plus deterministic tests may be sufficient.

Do not use “confirmed” when the experiment only showed correlation.

## Cross-game evidence

Samurai Heroes, Sumeragi and other MT Framework titles are valuable references. Label them as cross-game evidence. Do not silently promote a matching path, format name or controller pattern into Utage truth.

## AI-generated findings

AI assistance is welcome, but the model's prose is not evidence.

A finding produced by an AI should still identify the underlying code, bytes, test or runtime result. If another model proposed the idea, record it as provenance, then independently verify before promoting it to canon.

## Updating the canon

When a finding changes future engineering behaviour:

1. update code/tests if applicable;
2. update the relevant `.agents/skills`;
3. update the public canon or proven-failures document;
4. record the superseded assumption;
5. keep private/live game payloads out of Git.

That is how a conversation becomes durable research.
