# SCRA / rArchive Parent-Child Architecture — Live Utage proof — 2026-09-25

## Summary

The live English Utage tree contains small raw ARC members typed as `rArchive` (`0x73850D05`) whose payload begins with `SCRA`.

These are **not nested ARC files**. They are serialized child-archive membership manifests.

Live corpus proof:

- 117 SCRA descriptors found.
- all 117 use SCRA version 8;
- all 117 resolve to an existing child ARC;
- every manifest member list matches the referenced child ARC exactly;
- 507/507 manifest member references match child ARC type/path identities.

## Binary layout

All observed records use big-endian fields:

```text
0x00  char[4]  "SCRA"
0x04  u16      version        # observed: 8
0x06  u16      member_count
0x08  repeat member_count times:
      u32      resource_class_hash
      u32      resource_path_hash
```

Observed payload size is exactly:

`8 + member_count * 8`

## Hash identities

### Resource class hash

The first word in each pair is the MT Framework V2 resource-class hash:

`(~CRC32(class_name)) & 0x7FFFFFFF`

Example:

`rTexture -> 0x241F5DEB`

### Resource path hash

The second word is:

`(~CRC32(lowercase_internal_resource_path)) & 0xFFFFFFFF`

Unlike the class hash, the high bit is **not** masked away.

For live `pl000`, the SCRA pairs are exactly the four resource identities in the child `pl000.arc`, in child-table order.

## Proven parent families in the live ENG tree

### title_id.arc

- 31 SCRA child descriptors:
  `rom\eng\common\pl_face\pl000 ... pl029` plus the live family set.
- 123 total child member references.
- 112 unique referenced resource identities.
- those 112 unique identities are exactly `common\pl_face\pl_all.arc`:
  - same pair set;
  - same order;
  - 112/112 decompressed payloads identical.
- `title_id.arc` contains the same 112-resource manifested pool plus 39 non-manifest/title-specific resources and the SCRA descriptors.
- repeated child resources are deduplicated in the parent pool; 9 resource identities are referenced by more than one child manifest.

### quest/quest_id.arc

- 31 SCRA descriptors for `q000_id.arc ... q030_id.arc`.
- 274 manifest references, 172 unique resource identities.
- all 172 unique identities are present once in the parent pool.
- 36 identities are reused by multiple child manifests.
- no separate `quest_all.arc` exists in the live ENG quest directory.

### tenka/friend.arc

- 55 SCRA descriptors referencing `rom\jpn\pause\friend_*` child ARCs.
- 110 manifest references / 110 unique identities.
- all 110 are present in the parent pool.
- the child route can differ from the host route: an ENG parent can explicitly manifest JPN-path children.

## Parent payload comparison

Across the three proven parents:

- 507/507 manifested identities are present in the parent pool.
- 422/507 parent payloads are decompressed-byte-identical to the current child ARC.
- 85/507 differ in the current live build.
- all 85 divergences are `rTexture`:
  - 66 `id\texture\jpn\cp_name_pl\...`
  - 19 `id\texture\jpn\cp_name_nak\...`
- by parent:
  - `title_id.arc`: 123 equal / 0 divergent
  - `quest_id.arc`: 244 equal / 30 divergent
  - `tenka\friend.arc`: 55 equal / 55 divergent

The divergences are a **live-state QA fact**, not automatically a bug. Runtime/provider evidence is still required before choosing which side is authoritative.

## Architectural interpretation

The evidence supports this bounded model:

1. small child ARCs define normal resource groups;
2. an aggregate/resident parent stores a deduplicated resource pool;
3. SCRA records recreate each child ARC's logical membership as ordered `(type_hash,path_hash)` references into that resource identity space;
4. one physical parent resource may therefore serve multiple logical child manifests.

For the pl_face family, `pl_all.arc` is a byte-proven explicit aggregate corresponding to the unique SCRA pool embedded in `title_id.arc`.

This explains why a resident parent can appear to contain "duplicates" of many child ARCs without literally embedding those ARCs.

## Engineering consequence

When a resource belongs to an SCRA-manifested child family:

- do not assume the child ARC is the only mutation surface;
- resolve the SCRA parent(s);
- resolve any explicit aggregate such as `pl_all.arc`;
- compare all copies before mutation;
- use runtime evidence to decide the effective provider/synchronization set;
- after patching, validate the intended family for drift.

SCRA proves a structural relationship. It does **not**, by itself, prove runtime load precedence.

## Public source cross-check

REvilLib and UMVC3 tooling independently identify `0x73850D05` as `rArchive`. The Utage EBOOT contains reflection strings including:

- `ResourceNum`
- `TotalSize`
- `ResourceList`
- `Resources`
- `rArchive::CompressStream`
- `rArchive::DecompressStream`
- `rArchive`

No checked public implementation currently exposes an SCRA parser, making the SCRA layout and live parent-child mapping a BASARA Foundry result.


## Samurai Heroes control experiment

Official Samurai Heroes provides an independent localized control for the shared friend/pause family.

Read-only validation of SH `rom\eng\tenka\friend.arc` established:

- 51 raw `rArchive` / SCRA manifests;
- all 51 use SCRA version 8;
- all 51 point to `rom\eng\pause\friend_*` children;
- every manifest contains 6 member identities;
- 51/51 manifest tables exactly match the referenced child ARC tables;
- 306/306 manifested identities are present in the SH parent pool;
- 306/306 parent decompressed payloads are byte-identical to the corresponding English child payload;
- zero parent/child divergences.

This is important because it demonstrates that Capcom's official English localisation preserved SCRA parent/child payload identity rather than intentionally giving the same logical resource identity different localized artwork in parent and child.

### Bundle-shape boundary

The SH and Utage child archives are not interchangeable as whole containers.

Example `friend_000.arc`:

Utage JPN child:
- `rTexture` cp_name_pl
- `rTexture` cp_face_msg

Samurai Heroes ENG child:
- English `rTexture` cp_name_pl
- shared/JPN `rTexture` cp_face_msg
- `rMessage` GSM
- `rMessageInfo` FIM
- second `rMessage` GSM (_r)
- second `rMessageInfo` FIM (_r)

Therefore a compatible SH texture may be a valid donor while the whole SH child ARC is **not** a structurally equivalent donor.

## Localized ENG divergence diagnosis

The 85 current Utage ENG parent/child divergences are patch-introduced, not present in pristine/current JPN and not mirrored by official SH localization behaviour.

Representative decoded examples:

- `quest_id.arc` parent `cp_name_pl_022`: custom illustrated English "SASUKE SARUTOBI" plate.
- manifested `q000_id.arc` child: simple English "Sasuke Sarutobi" lettering.
- official SH homolog: simple English "Sasuke Sarutobi" lettering.
- `tenka\friend.arc` parent `cp_name_pl_000`: custom illustrated English "Masamune Date" plate.
- manifested Utage JPN child: Japanese nameplate.
- official SH homolog: clean English text.
- `tenka\friend.arc` parent `cp_name_nak_009`: English text with the known magenta/green corruption appearance.
- manifested child/pristine JPN: clean Japanese.
- official SH homolog: clean English names.

For the 85 divergent identities:
- 76 have exact-name SH English homologs;
- 9 do not have an exact SH path (Utage-exclusive nameplate identities);
- none of the 76 current Utage parent or child payloads is byte-identical to the SH payload, so these are not simple untouched SH donor copies.

### Engineering consequence

Treat a localized payload divergence inside an SCRA family as a **synchronization QA finding** until proven intentional by runtime/controller evidence.

Do not mass-copy the child, the parent, or a whole SH ARC. Resolve the intended visible design and runtime provider, then synchronize the compatible logical resource family at the member level.

For base-game nameplate identities, SH supplies an official English visual/reference donor candidate. Utage-exclusive identities still require Utage-specific/custom production.


## Public validator

A read-only validator now lives at:

`project/Foundry/tools/scra_validate.py`

It parses SCRA descriptors, resolves child ARC paths, validates exact child membership, and can optionally compare parent-vs-child decompressed payload identity.
