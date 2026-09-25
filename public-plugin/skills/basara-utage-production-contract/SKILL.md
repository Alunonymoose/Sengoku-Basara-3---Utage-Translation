---
name: basara-utage-production-contract
description: Universal public BASARA Foundry production contract. Use for any Sengoku BASARA 3 Utage patch, repair, texture, ARC, MSG, layout, QA or runtime task so fresh live files, approval identity, minimal mutation and final-artifact validation cannot be bypassed by model/tool routing.
---

# BASARA Foundry Production Contract

This skill is intentionally model-agnostic. A ChatGPT account, Codex session, Claude/Grok/DeepSeek handoff or human operator can use the same contract.

## Authority

1. Fresh user-supplied/current game bytes are **LIVE INPUT** and win for mutation.
2. Current public Foundry canon guides architecture but never substitutes for live production bytes.
3. Samurai Heroes or other game resources are references/donors only when the user lawfully supplies them.
4. Historical backups/checkpoints are evidence, not implicit production inputs.
5. Never ask for a usable file already present in the active task.

## Task fidelity

Deliver the requested production object, not an easier proxy:

- patch/fix/rebuild/root-ready -> actual mutated binary/archive and installation-ready package;
- texture/atlas repair -> exact source-compatible candidate, not a screen concept;
- QA -> direct inspection and evidence-ranked findings;
- location/owner query -> concrete path/provider evidence first;
- runtime diagnosis -> a discriminating test/evidence result, not filename intuition.

## Immutable production states

Keep these states separate:

`LIVE_INPUT -> DECODED_SOURCE -> PROVEN_EDIT_REGION -> CANDIDATE -> APPROVED_CANDIDATE -> ENCODED_RESOURCE -> FINAL_ARC -> VALIDATED_ARTIFACT -> ROOT_READY -> RUNTIME_TESTED`

Never treat a mockup as a candidate, a candidate as approved, an intermediate rebuild as final, or a static decode as runtime proof.

## Creative-tool lock

For an in-game texture/UI/atlas request, do not start with generic image generation.

Required order:

1. inspect/extract/decode the live resource;
2. prove dimensions, orientation, channel/material semantics and exact editable region;
3. identify separate neighbouring resources;
4. freeze everything outside the mutation region;
5. generate/draw only the isolated artwork required for the proven region;
6. composite it deterministically into the exact decoded source;
7. present that exact source-compatible atlas/sheet as the candidate;
8. derive any in-context preview from the candidate;
9. obtain approval for new custom artwork;
10. encode/rebuild from those exact approved pixels.

A whole-screen mockup must never become the source of production pixels unless the whole screen is itself the proven production resource.

## Candidate quality gate

Do not surface a candidate merely because a generator returned it. Reject/rework candidates with objectively wrong crop/aspect, extra UI chrome, broken lettering, malformed objects, wrong transparency, wrong orientation, neighbouring-slot contamination, or destructive scaling relative to the proven region.

## Mutation lock

Before binary mutation, define the smallest allowed mutation set. Everything else is protected. After rebuilding, re-extract/reparse the final artifact and compare protected content. Unexplained drift is failure.

## Approval lock

Approval freezes the exact candidate pixels/bytes. Do not regenerate, restyle, sharpen, recolour or reinterpret approved artwork during encoding unless the user explicitly reopens the art stage.

## Evidence language

Use only the highest state actually earned:

`HYPOTHESIS | STRUCTURALLY VERIFIED | VISUALLY VERIFIED | RUNTIME OBSERVED | RUNTIME PROVEN`

Do not call something fixed solely because a workspace intermediate looks correct.

## Fail closed, but not lazy

Use available files, code, tests and proven transforms before declaring a blocker. Stop only when a concrete missing fact or failed verification makes production unsafe. State the exact blocker.
