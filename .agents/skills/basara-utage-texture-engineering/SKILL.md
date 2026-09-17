---
name: basara-utage-texture-engineering
description: Production engineering workflow for Sengoku BASARA 3 Utage PS3 ARC/TEX/XET texture work, BC3 block grafting, RBxG format 0x2B, atlas edits, shared-owner rebuilds, and layout-aware verification. Use whenever editing or rebuilding game textures or their owning ARCs.
---

# BASARA Utage Texture Engineering

Use this skill for actual texture/UI engineering, not just image generation.

The user's explicit instructions take precedence over this skill. Do not add confirmation gates beyond the project's existing approval-first artwork rule.

## Non-negotiable completion rule

A texture task is not complete when an image exists.

The production chain is:

`resolve owner -> freeze source -> decode -> prepare candidate -> user visual approval -> explicit edit mask -> certified texture encode/graft -> target-shell preservation -> owning ARC rebuild -> extract/decode built resource -> verify confinement -> runtime test when required`

Return or deploy the rebuilt ARC(s), not merely PNGs.

## Always start from the live target

For normal incremental localisation, the current live English target resource is the preservation base.

Correct invariant:

`current live target + approved edit -> current live target with only approved touched BC blocks changed`

Pristine Japanese artwork is reference/repair input, not the normal untouched-art base.

Do not let a new edit revert earlier English work elsewhere in the same atlas.

### Explicit restore mode

A pristine official counterpart may be used as the artwork base only for an explicit repair/restore transaction where restoring damaged areas is intentional and auditable.

Keep normal incremental edit and pristine restore as separate modes/APIs.

## Target shell rule

The selected current target XET owns output container identity.

Preserve target header/shell/non-payload bytes unless a separately certified writer intentionally changes them.

A pristine counterpart may supply reference imagery or, in explicit restore mode, artwork payload blocks. Never transplant the pristine whole XET shell into the live English target.

## XET safety gate

Before writing, verify at minimum:

- magic is `00 58 45 54` (`\0XET`)
- dimensions are valid
- format is explicitly supported for the intended operation
- texture offset is within the resource
- declared top-level payload fits
- swizzle path is certified
- mip/trailing-data behavior is certified

Fail closed on unsupported swizzle, unknown write format, multi-mip resources without a full writer, or unexplained trailing data.

## Known texture-format handling

Treat format labels as project evidence, not generic DirectX truth.

### Plain BC paths

Ordinary BC1/BC3 decoding may be used only for format IDs the current Foundry code and fixtures explicitly certify.

Writing support is intentionally narrower than reading support.

### Format 0x15

Treat as ambiguous/fail-closed for writing unless a real Utage fixture proves the exact BC semantics.

Do not silently map an ambiguous format to BC3 just because the byte size fits.

### Format 0x19

Do not override Utage-specific evidence with a generic MT Framework table. Inspect current Foundry fixtures/canon before changing its mapping.

### Format 0x2B / RBxG

Do not expose 0x2B as ordinary artist-facing RGBA.

The stored payload is BC3, but the editing representation has special channel semantics.

For a decoded stored-channel pixel `(R,G,B,A)`, the proven project representation is:

`base = (A,A,A,G)`

`mask = (R,B,0,255)`

Reconstruction back to stored channels is:

`stored = (mask.R, base.A, mask.G, base.G)`

Project observation aligns with:

- green controlling opacity
- alpha controlling brightness/luminance-like visible intensity

Preserve hidden R/B information through the mask plane. Do not implement 0x2B as a naive G/A swap.

Generic one-PNG RGBA writes to 0x2B must fail closed. Use a dedicated RBxG path with base+mask representation and verification.

## BC-compressed edit-mask rule

BC1/BC3 modify 4x4 blocks.

For an approved pixel edit mask:

1. Expand the mask to the set of intersecting 4x4 blocks.
2. Validate that the candidate does not contain unapproved pixel changes inside touched blocks.
3. Encode/rebuild only the touched block set for the surgical graft path.
4. Copy every untouched compressed block from the chosen preservation base byte-for-byte.
5. Assert unchanged blocks are byte-identical after graft.
6. Decode the final resource and prove no pixel delta outside the effective touched-block mask.

A candidate is allowed to differ in wholly untouched blocks if those blocks are never imported; the live target block bytes still win. A candidate must not hide unapproved differences inside a touched block, because those differences would be encoded with the approved edit.

Record at least:

- total blocks
- touched/replaced blocks
- block coordinates
- exact mask pixel count
- compression collateral pixels inside touched blocks
- outside-effective-mask pixel delta

## Full-atlas encoder use

It is acceptable to run a deterministic BC encoder over the complete candidate and take only selected independent BC blocks if:

- block ordering is certified linear for the fixture
- no mipmaps are generated
- no error diffusion/state crosses BC blocks
- channel representation is correct for the format
- only approved block bytes are imported

Touched blocks do not need to be byte-identical to Capcom's original compressor; they do need to decode/render correctly.

## ARC v8 rebuild rules

For the certified PS3 ARC v8 path:

- on-disk magic: `\0CRA`
- table entry size: 80 bytes
- preserve names/order/type hashes/low flag bits
- untouched stored payloads must remain byte-identical
- replacement member must round-trip to requested raw bytes
- source ARC remains immutable
- output is a sibling/build ARC

Fail closed if the archive contains unexplained non-zero bytes in padding/gaps/trailers that the writer cannot preserve semantically.

Do not infer a universal compression rule from `compressedSize != rawSize` without corpus evidence. Unsupported/non-zlib compressed entries must fail rather than be guessed.

## Shared-owner textures

If a texture/resource has multiple live owners:

- enumerate the complete owner set
- require compatible/identical current target resources where the synchronized transaction requires it
- generate one final resource state
- rebuild every required owner ARC in one grouped transaction
- bind all outputs in the group audit
- fail the entire promotion if one owner fails verification

Never ship only one owner of a known shared texture.

## Layout-aware review

Before patching UI art, inspect the owning PSL/LSP/controller when available.

Use known fixture geometry to preview scale/cropping/placement. The historic 2x relationship between logical layout coordinates and atlas pixels is a fixture-backed heuristic, not a universal parser rule.

Do not claim a generic PSL/LSP writer exists unless current Foundry actually implements and tests it. A read-only PSL parser is not a certified layout mutation pipeline.

## Approval-first art workflow

Before production encode:

1. Render or reconstruct the complete exact-size candidate atlas.
2. Preserve unrelated artwork/alpha/coordinates.
3. Show the candidate to the user.
4. Prefer an in-layout mockup using the actual owner/controller.
5. After approval, freeze candidate and mask hashes and perform the production transaction.

If the user asks to alter artwork again, produce a new candidate and re-approve before rebuilding the final ARC.

## Production audit requirements

Bind the transaction to hashes for the relevant inputs/outputs, including where available:

- source ARC
- current target resource
- pristine/reference resource
- candidate art/planes
- edit mask
- final resource
- output ARC(s)

Verification should distinguish software proof from human visual approval.

## Runtime acceptance

A production-capable implementation is not automatically a runtime-certified asset.

For a new format/path, require a real Utage fixture and, when gameplay/render behavior matters, an RPCS3/PS3 test tied to the exact output build/hash.

Particularly for 0x2B/RBxG, do not call the generic write path runtime-certified until a real Utage resource has passed decode/edit/rebuild/extract/runtime verification.

## Known failure patterns to prevent

- returning only a PNG instead of rebuilding the ARC
- full-atlas recompression that changes unrelated art
- using pristine Japanese blocks as the default incremental base
- naive 0x2B RGBA/G-A swapping
- speculative Morton/8x4 swizzle on linear fixtures
- stale target ARC
- matching-name donor transplant from Samurai Heroes/Sumeragi
- synthetic-only proof being called production verification
- modifying one owner of a shared texture
- skipping final extraction/decode from the rebuilt ARC
