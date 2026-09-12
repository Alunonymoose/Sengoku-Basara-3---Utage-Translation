# Product Contract — BASARA Foundry v0.1

Foundry is approved as a fresh, Utage-first, screen-first translation workstation.

The product is successful only when it makes high-quality translation work more obvious, visual, reversible, attributable and difficult to damage accidentally.

## First vertical slice

The first milestone is one production path:

`problem/asset -> source identity -> JP/ENG/SH comparison -> protected candidate -> encoded-result review -> human approval -> verified ARC build -> runtime evidence`

The first target is the cockpit/roulette family, with `roulette_000_ID_HQ` as the reference problem asset.

## Non-negotiable rules

- Alrummi is not modified to become Foundry.
- Canonical source roots are read-only.
- No production art without human approval.
- No unexpected pixel changes outside an explicit edit mask.
- No binary writer is considered safe merely because its reader works.
- No exact PSL/LSP placement preview until geometry is actually decoded and fixture-tested.
- No autonomous mass translation or mass artwork generation in v0.1.
- Every meaningful build records provenance and the source fingerprints it was built against.
- Runtime Verified requires evidence from the game, tied to the exact build.

## v0.1 release gate

1. Real PS3 Utage ARC opens safely.
2. `roulette_000` can be located and rendered.
3. JP/current ENG/SH references can be compared in one workspace.
4. Candidate changes are deterministic and mask-scoped.
5. The encoded result is decoded and reviewed before approval.
6. Unrelated ARC members remain unchanged where the format permits.
7. Source drift invalidates stale recipes.
8. Malformed inputs fail without damaging project/source data.
9. The UI stays responsive while indexing/parsing work is isolated.
10. A runtime screenshot can be attached to the exact built asset as verification evidence.

Until these pass, feature expansion is secondary.
