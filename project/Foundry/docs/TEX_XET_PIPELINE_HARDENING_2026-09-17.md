# TEX/XET Pipeline Hardening — 2026-09-17

## Scope

This checkpoint hardens the existing BASARA Foundry texture transaction after an adversarial review of the current `foundry-v0.1` implementation. It does **not** claim runtime verification. The acceptance order remains:

`source identity -> candidate/mask approval -> software-verified sibling ARC -> final encoded-result human review -> exact-build cold boot -> runtime promotion`.

## Confirmed defect fixed: pristine-base regression

The previous `UtageSingleEntryXetGraft` always used the pristine counterpart payload as the untouched-art base. For incremental localisation this could silently restore Japanese/pristine blocks over already-approved English work elsewhere in the same atlas.

The transaction is now explicitly split:

- `CurrentTarget` — default production/incremental mode. Untouched BC blocks come from the current live target XET.
- `PristineRestore` — explicit repair/restore mode. Untouched BC blocks intentionally come from the pristine counterpart.

`IncrementalTargetPreservationRegression` proves that an existing live modified block survives byte-for-byte when a different block is edited, even when the candidate sheet is based on older/pristine artwork.

## Touched-block mask semantics

The production writer replaces only 4x4 BC blocks intersecting the explicit edit mask.

- A candidate difference outside the exact edit mask **inside a touched block** is rejected because it would be encoded into that replacement block.
- A candidate difference in a completely untouched block is ignored. The candidate is only a source for touched blocks; the live graft-base compressed bytes are copied verbatim elsewhere.

This distinction allows safe use of an older/pristine candidate sheet without reverting unrelated live atlas state.

## XET format hardening

- `0x15` remains BC2/BC3-ambiguous and is now fail-closed rather than guessed as DXT5.
- `0x19` remains mapped to BC1/DXT1 based on existing Utage-specific fixture evidence; generic MT tables do not supersede game-specific evidence.
- `0x2B` is BC3 storage with PS3 RBxG artist-channel semantics.

### RBxG contract

`UtageRbxgCodec` implements the externally corroborated transform:

Stored BC3 RGBA `(R,G,B,A)` -> artist planes:

- base = `(A,A,A,G)`
- mask = `(R,B,0,255)`

Repack:

- stored = `(mask.R, base.A, mask.G, base.G)`

Plain-RGBA writing of `0x2B` is refused. `ReplaceRbxgSingleLevel` is the dedicated channel-aware single-level codec path. Generic production ARC grafting for `0x2B` remains fail-closed until the dedicated RBxG block-graft transaction is exercised against a real Utage fixture and promoted by evidence.

## XET packed dimensions

The red-team report claimed Foundry's packed `block8` dimensions contradicted the older public PS3 parser. That claim was not accepted as a format defect.

For valid constraints implied by the older parser (`mip < 64`, width divisible by 4, even height), Foundry's bitfield model:

`packed = mip + (width << 6) + (height << 19)`

is compatible with the older three-byte formulas:

`width = (value & 0xFFF) * 4`

`height = (value >> 12) * 2`.

A real-fixture differential regression is still desirable, but there is no basis in this review to rewrite the current parser.

## ARC hardening

`UtageArcWriter` now:

- preserves protected entry bytes and low packed flag bits,
- continues to verify untouched stored member payloads byte-for-byte,
- refuses rebuilds containing unexplained non-zero bytes in inter-member gaps,
- refuses unexplained non-zero data after the final member,
- preserves the length of a zero-valued trailer.

The existing raw-vs-zlib inference is **not** redefined here from speculative flag semantics. A real corpus/fixture must establish any additional ARC compression modes before the generic writer changes its compression-kind model.

## Regression coverage added

- `IncrementalTargetPreservationRegression`
- `RbxgRegression`
- `ArcOpaqueRegionRegression`
- historical target-shell restore regression made explicitly `PristineRestore`
- existing graft test updated so unmasked changes within touched blocks fail, while completely untouched candidate blocks are not treated as production input

## LSP/PSL scope

Foundry has a fixture-proven/read-only PSL parser for known layout families, including the title fixture. This checkpoint does not introduce a generic certified PSL/LSP writer. Documentation must not imply that arbitrary layout mutation is globally production-safe.

## Evidence state

After merge, bind this checkpoint to the exact merged commit and Foundry CI run in the Drive canon.

- Code/build/synthetic regression status: pending CI at authoring time.
- Real `0x2B` Utage fixture round-trip: pending.
- Generic ARC exotic-compression corpus proof: pending.
- Generic PSL/LSP write capability: not implemented/certified.
- Runtime cold boot: per output/build, always pending until user evidence exists.
