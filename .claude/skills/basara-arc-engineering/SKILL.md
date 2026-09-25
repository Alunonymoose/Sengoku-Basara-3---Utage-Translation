---
name: basara-arc-engineering
description: Inspect, compare, modify, rebuild and validate live Sengoku BASARA 3 Utage ARC archives using a strict mutation budget and final-artifact verification.
---

# Utage ARC engineering

Apply the BASARA production contract first.

## Live-source lock

Only mutate a LIVE MASTER.
A fresh active file wins over Drive/checkpoint copies for file truth.
Never ask the user to resend a usable live ARC already present.

## Mutation budget

Before editing define:
- input path/hash
- ARC version/member count
- exact internal member indexes/paths allowed to change
- reason for each allowed change
- protected members

Everything not explicitly in the budget is protected.

## Ownership evidence

Weight evidence:
1. controlled runtime/load evidence
2. exact layout/reference linkage
3. live container membership + duplicate mapping
4. proven resident/preload rule for that family
5. SH homologous architecture
6. naming similarity only as hypothesis

Containment alone is not runtime authority.
Do not mass-edit duplicate internal names without proven equivalence/provider evidence.

## Texture handoff

If an ARC change involves custom texture art, complete the texture-engineering candidate/approval gate before ARC mutation.

Do not generate a whole-screen concept and attempt to import it.

## Donor policy

Prefer:
1. exact compatible Samurai Heroes donor
2. proven English live-Utage sibling
3. custom Utage reconstruction

When a donor needs companion LSP/PSL/text/metrics, treat it as a resource set.

## Safe transaction

1. identify/hash live input
2. parse/extract deterministically
3. establish mutation budget
4. patch only approved/proven members
5. rebuild with the known-compatible ARC path
6. reparse/re-extract the FINISHED ARC
7. verify changed members
8. compare protected members to baseline
9. fail on unexplained path/count/codec/protected drift
10. package/test according to achieved evidence

## Duplicate synchronization

Synchronize only a proven runtime-equivalence/provider family.
Keep the owner list and reason.
Never generalize one title/title_id or other preload result to unrelated families.

## Delivery

A requested final patch normally ends in one installation-ready ROOT-READY ZIP with correct game-root paths and a concise manifest.

Loose ARC/TEX/XET/PNG files are not the default final deliverable unless explicitly requested.

Never call an archive final merely because it rebuilt successfully; validate the stored result from the finished archive.
