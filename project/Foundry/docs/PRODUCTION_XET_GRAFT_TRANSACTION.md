# Production XET graft transaction

Foundry production texture writes are fail-closed transactions. The source ARC is immutable input; successful work produces a sibling ARC plus audit JSON.

## Certified path

1. Re-read the source as PS3 Utage ARC v8.
2. Target exactly one member and require the certified texture type hash.
3. Decompress that member and use it as the pristine XET base.
4. Run `UtageBc3BlockGraft.GraftTopLevel` with the candidate RGBA and explicit edit mask.
5. Refuse the transaction unless `Bc3GraftReport.Ok` is true.
6. Rebuild the ARC through `UtageArcWriter` with exactly one replacement.
7. Re-read the sibling ARC and decompress the target member.
8. Require byte-for-byte equality with the grafted XET.
9. Emit SHA-256 source/output fingerprints and an indented audit JSON document.
10. Only the resulting `AssetApprovalEvidence` may be used to cross the `Approved` boundary.

## API

```csharp
var tx = UtageSingleEntryXetGraft.BuildSibling(
    sourceArc,
    memberIndex,
    candidateRgba,
    editMask01);

AssetApprovalGuard.EnsureCanTransition(
    AssetApprovalState.Review,
    AssetApprovalState.Approved,
    tx.ApprovalEvidence);
```

## Non-negotiable rules

- Never overwrite the canonical/source ARC in this operation.
- Never use `UtageXetCodec.ReplaceSingleLevel` as the production texture writer.
- Never approve a texture candidate from visual appearance alone.
- Never bypass a failed outside-mask identity check.
- Never treat an ARC rebuild as verified until the target raw member round-trips to the exact grafted XET.

The synthetic graft smoke suite covers successful graft, outside-mask rejection, sibling ARC rebuild/round-trip, source-byte immutability, audit output, and approval-gate rejection without proof.
