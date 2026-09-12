# Production XET graft transaction

Foundry production texture writes are fail-closed transactions. The source ARC is immutable input; successful work produces a sibling ARC plus audit JSON.

## Certified path

1. Re-read the source as PS3 Utage ARC v8.
2. Target exactly one member and require the certified texture type hash.
3. Choose the artwork base:
   - preferred: `pristineXetOverride` (unique JPN / counterpart XET, layout-matched);
   - fallback: decompressed target member (only when it is trusted as pristine art).
4. Run `UtageBc3BlockGraft.GraftTopLevel` with the candidate RGBA and explicit edit mask.
5. Refuse the transaction unless `Bc3GraftReport.Ok` is true.
6. Rebuild the ARC through `UtageArcWriter` with exactly one replacement (writer also proves untouched stored payloads).
7. Re-read the sibling ARC and decompress the target member.
8. Require byte-for-byte equality with the grafted XET.
9. Emit SHA-256 source/output fingerprints and an indented audit JSON document.
10. Build `AssetApprovalEvidence` only via `AssetApprovalEvidence.ForUtageBc3GraftArc` (bound hashes + allowlisted proof kind).
11. Optional: `UtageSiblingArcStore.Write` → `{stem}.foundry.arc` + `.audit.json` (never overwrites source).

## API

```csharp
var tx = UtageSingleEntryXetGraft.BuildSibling(
    sourceArc,
    memberIndex,
    candidateRgba,
    editMask01,
    pristineXetOverride: jpnXet); // preferred

AssetApprovalGuard.EnsureCanTransition(
    AssetApprovalState.Review,
    AssetApprovalState.Approved,
    tx.ApprovalEvidence);

var disk = UtageSiblingArcStore.Write(sourceArcPath, tx);
```

Flat masks may be built from domain regions:

```csharp
var mask01 = EditMaskCodec.ToMask01(editMask, width, height);
```

## Non-negotiable rules

- Never overwrite the canonical/source ARC in this operation.
- Never use `UtageXetCodec.ReplaceSingleLevel` as the production texture writer.
- Never approve a texture candidate from visual appearance alone.
- Never bypass a failed outside-mask identity check.
- Never treat an ARC rebuild as verified until the target raw member round-trips to the exact grafted XET.
- Never accept `AssetApprovalEvidence` with a non-allowlisted proof kind or missing ARC hash binding.

The synthetic graft smoke suite covers successful graft, outside-mask rejection, pristine override, sibling ARC rebuild/round-trip, source-byte immutability, audit output, forgeable-proof rejection, and disk sibling write.
