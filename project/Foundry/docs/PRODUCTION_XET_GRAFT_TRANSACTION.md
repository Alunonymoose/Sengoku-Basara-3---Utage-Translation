# Production XET graft transaction

Foundry production texture writes are fail-closed transactions. Canonical ENG/JPN source trees are immutable inputs; successful work produces a verified ARC plus audit JSON under the Foundry project build tree.

## Certified path

1. Re-read the selected ENG source as PS3 Utage ARC v8 and revalidate the exact indexed member name/type.
2. Resolve a **unique pristine counterpart** from the separately configured Japanese source route. Ambiguity is a hard stop.
3. Re-read that JPN ARC/member independently and require a certified texture resource.
4. Require target/pristine structural compatibility: XET version, dimensions, format, mip count, swizzle and texture offset.
5. For normal incremental localisation, use the **current live target XET compressed payload as the preservation base**. Pristine JPN remains mandatory structural/reference authority. Only an explicit restore/repair transaction may intentionally restore blocks from pristine.
6. Bind the frozen candidate RGBA to an explicit per-pixel edit mask against the current live target decode. A pristine comparison may still be shown as reference, but it is not the default production base.
7. Show both the exact changed-pixel mask and the minimum intersecting 4×4 BC3 block footprint. The operator must explicitly approve that mask before a production build can run.
8. Run `UtageBc3BlockGraft.GraftTopLevel` and refuse the transaction unless `Bc3GraftReport.Ok` is true.
9. Rebuild the ARC through `UtageArcWriter` with exactly one replacement; untouched stored member payloads remain byte-identical.
10. Re-read the built ARC and require the target raw member to equal the grafted XET byte-for-byte.
11. Emit audit schema 3 with source/output ARC hashes, target-resource hash, pristine-base hash, member identity, mask/block counts and verification flags.
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

- **Exact mask pixels** are the pixels the candidate intentionally changes relative to the reviewed current live target decode.
- **Affected BC3 blocks** are the minimum 4×4 compressed blocks intersecting that exact mask.
- Pixels inside an affected block but outside the exact mask are shown separately as **potential compression collateral**.
- Automatic delta detection may propose a mask; it must never silently approve one.
- Any change to candidate, pristine reference, selected asset, or mask invalidates the previous approval binding.

## Non-negotiable rules

- Never write production output into a canonical ENG/JPN source tree or beside the source ARC.
- Never use pristine JPN as the default untouched-art base for an incremental edit; doing so can erase earlier approved English work.
- Never use `UtageXetCodec.ReplaceSingleLevel` as the production texture writer.
- Never approve a texture candidate from visual appearance alone; review the exact mask and BC3 footprint.
- Never bypass a failed outside-mask identity check.
- Never treat an ARC rebuild as verified until the target raw member round-trips to the exact grafted XET.
- Never allow ordinary application/worker code to construct successful production approval evidence.
- Never claim a private fixture passed unless the raw ARC/XET fixture itself was actually exercised.

The synthetic graft suite covers exact-mask proposal math, BC3 block footprint/collateral reporting, outside-mask rejection, mandatory pristine-JP structural/reference compatibility, cumulative live-target preservation, single-entry ARC rebuild/round-trip, source-byte immutability, opaque approval evidence, audit output and external build-directory enforcement.

## Format-specific writer gate

BC3 storage alone does not imply ordinary RGBA channel semantics.

The generic one-RGBA writer must fail closed for:
- `0x2A`: use the dedicated Kuriimu2 `MtTex_YCbCrColorShader` transform path proven on `title_004_ID_HQ`;
- `0x2B`: use the dedicated RBxG base+mask path.

Until those dedicated paths are implemented and fixture-tested inside Foundry, the generic production writer is limited to the explicitly admitted plain-RGBA DXT5 format IDs.
