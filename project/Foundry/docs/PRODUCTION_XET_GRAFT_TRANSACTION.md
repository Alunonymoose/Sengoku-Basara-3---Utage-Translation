> **2026-09-26 CURRENT RULE:** the former mandatory-pristine-base transaction is superseded. Current code defaults to `--base-mode current`: CURRENT LIVE TARGET owns the shell and untouched blocks. `--base-mode restore` is the only mode allowed to use pristine/reference payload as the artwork base. For lossy BC custom art, approval is tied to the encoded→decoded candidate and its exact encoded/touched-block bytes.

# Production XET graft transaction

Foundry production texture writes are fail-closed transactions. Canonical ENG/JPN source trees are immutable inputs; successful work produces a verified ARC plus audit JSON under the Foundry project build tree.

## Certified path

1. Re-read the selected ENG source as PS3 Utage ARC v8 and revalidate the exact indexed member name/type.
2. Resolve a **unique pristine/reference counterpart** when available and require target/reference structural compatibility; ambiguity is a hard stop for transactions that depend on that reference.
3. Re-read the reference independently and require a certified texture resource when it participates in the transaction.
4. Default to `XetGraftBaseMode.CurrentTarget`: the current live target owns the shell and untouched artwork blocks. Use `PristineRestore` only for an explicit audited restore transaction.
5. Bind the frozen candidate RGBA to an explicit per-pixel edit mask and expand it only to intersecting 4×4 BC blocks.
6. Temporarily encode/graft and decode the candidate before human approval. Approval binds the exact encoded/touched-block bytes plus the decoded stored-result image; final production reuses those bytes rather than re-encoding.
7. Show both the exact changed-pixel mask and the minimum intersecting 4×4 BC3 block footprint. The operator must explicitly approve that mask before a production build can run.
8. Run `UtageBc3BlockGraft.GraftTopLevel` and refuse the transaction unless `Bc3GraftReport.Ok` is true.
9. Rebuild the ARC through `UtageArcWriter` with exactly one replacement; untouched stored member payloads remain byte-identical.
10. Re-read the built ARC and require the target raw member to equal the grafted XET byte-for-byte.
11. Emit the current audit schema with source/output ARC hashes, target-resource hash, selected preservation-base/reference hashes, base mode, member identity, mask/block counts and verification flags.
12. Create opaque `AssetApprovalEvidence` inside the certified Utage format assembly only; normal UI/Worker callers cannot mint a successful approval token.
13. Write ARC/audit output to an explicit Foundry project build directory. Writing over or beside a canonical source ARC is forbidden.

## API

```csharp
var proposal = UtageEditMaskProposalService.Create(
    pristineDecodedRgba,
    candidateRgba,
    width,
    height);

// Operator reviews proposal.Mask01 plus proposal.BlockCoords before build.

var tx = UtageSingleEntryXetGraft.BuildSibling(
    sourceArc,
    memberIndex,
    pristineJpnXet,
    candidateRgba,
    proposal.Mask01);

AssetApprovalGuard.EnsureCanTransition(
    AssetApprovalState.Review,
    AssetApprovalState.Approved,
    tx.ApprovalEvidence);

var disk = UtageSiblingArcStore.Write(
    sourceArcPath,
    tx,
    projectBuildArcPath);
```

Domain rectangle masks can also be converted explicitly:

```csharp
var mask01 = EditMaskCodec.ToMask01(editMask, width, height);
```

## Mask-review semantics

- **Exact mask pixels** are the pixels the candidate intentionally changes relative to the selected preservation-base decode (normally current live target; pristine only in restore mode).
- **Affected BC3 blocks** are the minimum 4×4 compressed blocks intersecting that exact mask.
- Pixels inside an affected block but outside the exact mask are shown separately as **potential compression collateral**.
- Automatic delta detection may propose a mask; it must never silently approve one.
- Any change to candidate, pristine reference, selected asset, or mask invalidates the previous approval binding.

## Non-negotiable rules

- Never write production output into a canonical ENG/JPN source tree or beside the source ARC.
- Normal incremental production MUST use the current live target as preservation base. Pristine/reference payload may become the base only in explicit `PristineRestore` mode.
- Never use `UtageXetCodec.ReplaceSingleLevel` as the production texture writer.
- Never approve a texture candidate from visual appearance alone; review the exact mask and BC3 footprint.
- Never bypass a failed outside-mask identity check.
- Never treat an ARC rebuild as verified until the target raw member round-trips to the exact grafted XET.
- Never allow ordinary application/worker code to construct successful production approval evidence.
- Never claim a private fixture passed unless the raw ARC/XET fixture itself was actually exercised.

The synthetic graft suite covers exact-mask proposal math, BC3 block footprint/collateral reporting, outside-mask rejection, current-target default base, explicit pristine-restore mode, corrupted-ENG isolation, single-entry ARC rebuild/round-trip, source-byte immutability, approval evidence, audit output and external build-directory enforcement.
