> **2026-09-24 TITLE_004 BC-ENDIAN HOTFIX — READ FIRST**
>
> A real current `title_004_ID_HQ` fixture plus the user's runtime screenshot disproved the 2026-09-24 synthetic assumption that Utage PS3 BC payload RGB565 endpoint words must be byte-swapped around BCnEncoder.Net. That swap produces the exact failure signature seen in game: a green rectangle with magenta/pink Sengoku artwork.
>
> For the verified Utage PS3 `0x2A` title path, the XET header/table fields remain big-endian, but the DXT5/BC3 payload uses **standard BC3 endpoint byte order**. Kuriimu2 registers PS3 `0x2A` as ordinary `ImageFormats.Dxt5()` plus `MtTex_YCbCrColorShader`; there is no separate PS3 RGB565 endpoint swap in that path.
>
> **Production rule:** never infer BC endpoint byte order from the XET/ARC container endianness. Decode the exact current live fixture with the intended production codec before any write. For `title_004`, that preflight must reproduce the known blue/transparent Sengoku baseline; a green/magenta decode is an automatic STOP and proves the codec path is wrong.
>
> **Base rule reaffirmed:** normal incremental localisation uses the **current live target payload** as the untouched-block base. Pristine/JPN is reference/compatibility evidence unless the transaction is explicitly marked restore/repair.
>
> Synthetic self-roundtrips cannot override contradictory real Utage fixture or runtime evidence.
>
> **2026-09-24 TEXTURE CODEC HARDENING SUPERSESSION — READ FIRST**
>
> The durable Foundry C# texture path has now been corrected to the current PS3 contract and supersedes older operational warnings that no current writer exists.
>
> - **SUPERSEDED by the hotfix above:** the temporary RGB565 endpoint byte-swap bridge was wrong for the verified Utage 0x2A/title_004 path. Standard BC3 payload byte order is required there.
> - `0x2A` is BC3 storage **plus** the Kuriimu2 PS3 YCbCr colour shader. Artist-facing preview/candidate APIs use normal display RGBA; codec storage is `(Cr, alpha, Cb, Y)`.
> - `0x15` is fixture-proven DXT3/BC2 for read/preview. Production writing remains blocked pending a real edit/rebuild/runtime fixture.
> - `0x2B` must not use generic one-plane RGBA; its dedicated RBxG/base+mask representation remains required and writing remains fail-closed.
> - Multi-mip, non-zero-swizzle, BC1-write, BC2-write and unsupported-format production remain fail-closed.
> - Foundry CI for the independent endpoint/shader fixture suite is green. This is software/fixture proof, not blanket runtime certification for newly built assets.
>
> Durable detail: `project/texture_tools/TEXTURE_CODEC_HARDENING_2026-09-24.md`.
> Current Python human-review decode uses the same visible `0x2A` shader semantics.
>
> Do not regress to either extreme: the old “raw YUV texture structure” theory is disproven, but treating 0x2A BC-decoded storage channels as ordinary artist RGBA is also wrong.

> **2026-09-23 XET SUPERSESSION — READ FIRST**
>
> The older format-specific sections below are retained as history but MUST NOT override the solved 2026-09-23 XET contract. The prior bespoke 0x2A raw-YCbCr / half-dimension / Morton interpretation is **DISPROVEN**: the resource is standard MT Framework block-compressed texture data whose payload was previously misread using half dimensions.
>
> Current solved corpus contract: standard texFlags width/height; 0x2A/0x17/0x15 decode as BC-compressed formats per current fixtures and Kuriimu2 mappings, 0x19 as BC1, 0x27 as A8R8G8B8. **Do not infer BC endpoint byte order from PS3 container endianness.** The verified 0x2A/title_004 path uses standard DXT5/BC3 endpoint byte order. Current fixture geometry: PSL +0x74..+0x80 destination rect, +0x84..+0x90 source min/max, with shipped _ID_HQ textures mapping at 2x SD coordinates.
>
> rom/jpn is NOT a guaranteed Japanese donor. Render/read candidates and prefer compatible official SH evidence. Production still preserves the CURRENT LIVE TARGET outside intended touched blocks. Use Donor Matcher V5.1 + Resource Ownership Analyzer before donor/provider decisions. The exact original xetenc.py is not yet durably persisted; custom writes remain gated on a recovered/revalidated current encoder path.
>

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

Before writing, **first decode the exact current live target with the same codec path that will be used for the write and compare it with known runtime/reference appearance.** This is a mandatory semantic preflight, not an optional preview. A codec that cannot reproduce the current live fixture is forbidden from producing a replacement.

For `title_004_ID_HQ`, the semantic preflight is specifically locked: the current live texture must decode as a blue Sengoku logo with transparent background/coverage. A green rectangle, magenta/pink logo, missing transparency, or other material-channel corruption is an automatic fail-closed signal.

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

### Format 0x2A / title-logo YCbCr — runtime verified on `title_004`

PS3 format `0x2A` is BC3/DXT5 storage with Kuriimu2's `MtTex_YCbCrColorShader` channel transform on the verified Utage title fixture.

For stored channels `(R,G,B,A)`:

- stored `G` = rendered alpha / coverage
- stored `A` = Y luminance
- stored `R` = Cr around neutral 123
- stored `B` = Cb around neutral 123

Exact Kuriimu2 read transform:

```text
alpha = G
Y  = A
Cb = B - 123
Cr = R - 123
outR = clamp(Y + 1.402*Cr)
outG = clamp(Y - 0.344136*Cb - 0.714136*Cr)
outB = clamp(Y + 1.772*Cb)
```

Exact Kuriimu2 write transform from normal RGBA:

```text
Y  = 0.299R + 0.587G + 0.114B
Cb = 123 - 0.168736R - 0.331264G + 0.5B
Cr = 123 + 0.5R - 0.418688G - 0.081312B
stored = (Cr, inputAlpha, Cb, Y)
```

#### Runtime-verified clean-edge rule for `title_004_ID_HQ`

On 2026-09-18 the clean Sengoku title repair was runtime visually verified and explicitly approved by the user. The accepted exact build is recorded in BASARA Foundry as `00 FINAL TITLE 0x2A RUNTIME VERIFIED — 2026-09-18` and under `04 Runtime Evidence/TITLE_004_RUNTIME_VERIFIED_2026-09-18`.

Accepted build hashes:

- source ARC: `201010cc5d4bbee203c5988f5c4827da18e09a91e87c83525debb94047bb75dd`
- final `title_004` XET: `978f00c5709edb4553473ba8b1b3ae6bd760a8517a5fdb34b0371125775a3808`
- final ARC: `6350620a27ab0dcd43fa695ef305a387bf8a3067be9d6cfa4489231266b11c82`
- root-ready ZIP: `fa4e3eb325a0c1bce75af22d8c8ed2e2738569870ea8aa53dd8648654727eb1c`

The runtime-verified reconstruction rule for this fixture is:

1. preserve the full grayscale antialiased alpha mask; never threshold it to binary alpha;
2. preserve the intended visible Sengoku blue/gradient;
3. prefill RGB beneath alpha-zero pixels with representative Sengoku blue before the 0x2A YCbCr transform, rather than leaving black transparent RGB to enter BC3 edge blocks;
4. convert with the exact Kuriimu2 write transform above;
5. BC3 encode deterministically;
6. graft only certified 4x4 blocks inside the fixture-proven `logo_sengoku` source rectangle, 184x88 logical = 368x176 HQ pixels;
7. preserve the target XET shell/header and every block outside that region byte-for-byte;
8. leave `title_005` and `title_006` untouched for a Sengoku-only repair unless newer evidence requires otherwise;
9. re-extract and decode the built XET before runtime use.

Do **not** regress this solved title path by writing conventional RGBA into 0x2A, globally forcing R/B to 123, using black RGB under transparent edge pixels, or rediscovering the channel semantics from generic MT Framework tables.

Scope: the 0x2A channel contract is source-verified and runtime-validated on `title_004`. The transparent-RGB edge-preconditioning strategy is runtime verified for this specific title fixture and approved art; inspect pristine/reference behavior before generalizing that artwork-specific edge strategy to unrelated 0x2A assets.

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
