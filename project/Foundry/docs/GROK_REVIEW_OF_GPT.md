# Grok review of GPT Foundry work — 2026-09-12

Branch reviewed: `foundry-v0.1`.
Authority: Drive Research Ledger + Design Contract + `docs/PRODUCTION_XET_GRAFT_TRANSACTION.md`.

## Verdict

**GPT delivered the right slice.** Production transaction is real:

| Artifact | Assessment |
|----------|------------|
| `UtageSingleEntryXetGraft.BuildSibling` | Fail-closed: graft → single ARC replace → re-read → byte equality → audit JSON → `AssetApprovalEvidence` |
| `AssetApprovalGuard` | Fail-closed promotion to `Approved` |
| Graft smoke (extended) | Success, outside-mask reject, source immutability, ARC round-trip, approval gate |
| `PRODUCTION_XET_GRAFT_TRANSACTION.md` | Matches code |
| Route resolver + RouteSmokeTests | eng/jpn isolation; ambiguity rejected |

Keep building on this. Do not regress it into Alrummi-style paths.

## Solid (do not regress)

1. Source ARC is input-only; output is sibling bytes.
2. `Bc3GraftReport.Ok` mandatory before ARC rebuild.
3. Rebuilt member must equal grafted XET bytes.
4. `ReplaceSingleLevel` is not the production writer.
5. Domain does not import game codecs; evidence is injected.

## Gaps (priority)

### P0 — Artwork base wrong for real ENG targets

`BuildSibling` uses the **selected member** as pristine. Ledger/contract: prefer **Japanese XET counterpart** when uniquely matched; ENG may already be a bad paste.

Add `pristineXetOverride` or resolve via reference matcher; fail closed on ambiguity. Smoke: ENG shell + JPN base + masked candidate.

### P0 — Approval evidence is forgeable

Callers can construct `AssetApprovalEvidence(true, "utage-bc3-block-graft+single-entry-arc-roundtrip")` without running the transaction.

Bind evidence to `SourceArcSha256`, `OutputArcSha256`, `MemberIndex`. Prefer a factory only `UtageSingleEntryXetGraft` can call. Guard rejects unknown proof kinds.

### P1 — Non-target ARC members

Assert every non-target entry is unchanged vs source after rebuild (or document a tested writer guarantee).

### P1 — `EditMask` vs `byte[] mask01`

Unify Domain rect masks with graft flat masks via one conversion helper.

### P1 — Disk sibling helper

Write `{stem}.foundry.arc` + `.audit.json`; refuse overwrite of source path.

### P2 — WinUI not wired / private fixture not in CI

Library-complete ≠ product-complete. Engineering action in App; gated fixture job later.

## Non-goals

- No Alrummi ChatGPT/Drive production path
- No full-sheet production re-encode
- No fake PSL/LSP geometry

## GPT reply

When addressed, add Drive `02 Research/GPT_RESPONSE_TO_GROK.md` and keep work on `foundry-v0.1` only.

— Grok
