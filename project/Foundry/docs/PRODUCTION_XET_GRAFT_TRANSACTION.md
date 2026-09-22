# Production XET graft transaction

Foundry production texture writes are fail-closed transactions. Canonical source trees are immutable inputs; successful work produces verified sibling ARC output plus audit evidence.

## Preservation model

Normal incremental localisation uses:

`current live target + approved edit -> current live target with only approved touched BC blocks changed`

Pristine Japanese is mandatory **reference/compatibility evidence**, not the default untouched-art base.

An explicit `PristineRestore` mode exists for intentional repair/restore transactions. It must never be selected implicitly.

## Certified path

1. Re-read the selected live target ARC and revalidate exact member name/type.
2. Resolve and re-read a unique pristine counterpart for structural/reference checks.
3. Require target/pristine XET compatibility: version, swizzle, reserved/alpha fields, dimensions, image/mip counts, format, unknown3, texture offset and top-level payload size.
4. Preserve the live target XET shell/header/non-payload bytes.
5. Freeze the approved candidate and explicit pixel edit mask.
6. Convert the mask to intersecting 4×4 BC blocks.
7. For normal incremental mode, use the **current target compressed payload** as the untouched-block base.
8. Candidate differences in completely untouched blocks are ignored; those live target block bytes remain authoritative.
9. Candidate differences inside a touched BC block but outside the exact approved mask are rejected.
10. Use the format-aware encoder:
   - ordinary 0x17/0x18 BC3: direct RGBA -> BC3;
   - 0x2A: display RGBA -> exact PS3 MT YCbCr shader -> BC3;
   - 0x2B: production write currently fail-closed pending real-fixture certification;
   - 0x15: ambiguous and fail-closed.
11. Replace only approved compressed blocks.
12. Decode the final resource in **display space** and prove zero pixel delta outside the effective touched-block footprint.
13. Rebuild the ARC; every untouched stored ARC member must remain byte-identical.
14. Re-read the built ARC and require the target raw member to equal the final XET byte-for-byte.
15. Bind source ARC, target XET, pristine reference, candidate, mask, final XET and output ARC hashes in the audit.
16. Final encoded-output human review remains separate from software proof.

## API

Normal incremental production:

```csharp
var tx = UtageSingleEntryXetGraft.BuildSibling(
    sourceArc,
    memberIndex,
    pristineReferenceXet,
    approvedCandidateRgba,
    approvedMask01);
```

Explicit pristine restore:

```csharp
var tx = UtageSingleEntryXetGraft.BuildSibling(
    sourceArc,
    memberIndex,
    pristineReferenceXet,
    approvedCandidateRgba,
    approvedMask01,
    createdAtUtc,
    XetGraftBaseMode.PristineRestore);
```

The default five-argument overload is `CurrentTarget`.

## Format semantics

### Stored vs display RGBA

`UtageXetCodec.DecodeTopLevel` exposes physical BCn stored channels.

`UtageXetCodec.DecodeDisplayTopLevel` is the artist/review boundary. For 0x2A/0x2B it applies the PS3 MT Framework YCbCr shader used by Kuriimu2.

Do not compare artist candidates to raw stored 0x2A channels.

### 0x2A

0x2A is BC3 storage with the exact Kuriimu2 PS3 YCbCr transform:

- stored G = display alpha
- stored A = Y
- stored R = Cr + 123
- stored B = Cb + 123

Production uses the dedicated YCbCr editing path; generic plain-RGBA writing is rejected.

### 0x2B

Kuriimu2 applies the same PS3 YCbCr display shader to 0x2B.

Historical project RBxG/base+mask handling is a lossless **stored-channel decomposition**:

- base = (stored.A, stored.A, stored.A, stored.G) = (Y,Y,Y,alpha)
- mask = (stored.R, stored.B, 0, 255) = (Cr+123,Cb+123,0,255)
- reconstruction = (mask.R, base.A, mask.G, base.G)

This does not conflict with YCbCr; it preserves the underlying channels separately. Until a real Utage 0x2B edit/rebuild/runtime fixture is certified, production writing remains fail-closed.

## Non-negotiable rules

- Do not overwrite canonical source ARCs.
- Do not use pristine JPN as the normal incremental preservation base.
- Do not transplant a pristine/donor whole XET shell.
- Do not use plain RGBA writing for 0x2A or 0x2B.
- Do not guess 0x15 as DXT5.
- Do not write only one member of a proven shared-owner class.
- Do not accept candidate changes hidden inside touched blocks but outside the approved pixel mask.
- Do not call software verification human approval.
- Do not skip final extract/decode from the rebuilt ARC.

## Regression coverage

The texture hardening suite includes:

- incremental live-target preservation across untouched BC blocks;
- explicit pristine-restore behavior;
- target-shell preservation;
- synchronized shared-owner handling;
- exact PS3 YCbCr transform checks;
- plain-writer rejection for 0x2A/0x2B;
- 0x2B production fail-closed behavior;
- 0x15 ambiguous-format fail-closed behavior.
