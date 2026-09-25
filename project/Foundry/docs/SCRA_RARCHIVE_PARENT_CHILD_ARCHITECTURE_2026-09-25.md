# SCRA / rArchive Parent-Child Manifest Architecture — 2026-09-25

## Summary

Live Utage evidence shows that certain parent/preload ARCs contain raw `rArchive` resources whose payloads begin with `SCRA`. These are not nested ARC files. They are compact manifests describing the exact member identities of a child ARC.

Observed live parents:

- `rom/eng/title_id.arc` -> 31 `rom/eng/common/pl_face/pl000..pl030` child manifests
- `rom/eng/quest/quest_id.arc` -> 31 `rom/eng/quest/q000_id..q030_id` child manifests
- `rom/eng/tenka/friend.arc` -> 55 `rom/jpn/pause/friend_*` child manifests

Across the current live ENG tree, **117/117 SCRA manifests exactly match their referenced child ARC member lists**.

## Binary structure

For the observed PS3 Utage records:

```text
offset  size  meaning
0x00    4     "SCRA"
0x04    2     big-endian version (observed 8)
0x06    2     big-endian member count
0x08    ...   member records, 8 bytes each
```

Each 8-byte member record is:

```text
u32be resource_class_hash
u32be resource_path_hash
```

The first word is the same MT Framework resource-class hash used by ARC table entries.

The second word is the **full 32-bit complemented CRC32 of the lowercased internal resource path**:

```text
path_hash = (~CRC32(lowercase(internal_path))) & 0xFFFFFFFF
```

Unlike the class hash, this path hash retains bit 31.

Example: the `pl000` SCRA resource contains four pairs and matches `pl000.arc` exactly:

```text
241F5DEB 34E2C6CE  id\texture\jpn\charasele_01\charasele_01_000_ID_HQ
241F5DEB F51E09E7  id\texture\jpn\charasele_02\charasele_02_000_ID_HQ
241F5DEB 4799A0EA  id\texture\jpn\kamon\kamon_000_ID_HQ
241F5DEB E755AC4C  id\texture\jpn\army\army_000_ID_HQ
```

## Parent payload relationship

Across all 117 manifests, the parent ARC contains every manifested resource identity: **507/507 resource pairs were present in the parent**.

Current live payload equality:

- `title_id.arc`: 123/123 manifested resources decompressed-byte-identical to child ARCs.
- `quest_id.arc`: 244 equal, 30 divergent.
- `tenka/friend.arc`: 55 equal, 55 divergent.

All 85 current divergences are `rTexture` resources:
- 66 under `id\texture\jpn\cp_name_pl`
- 19 under `id\texture\jpn\cp_name_nak`

This is strong evidence that these parent ARCs are **flattened/preloaded copies of child resources plus explicit child-archive manifests**. The manifest describes identity/membership; payload identity can diverge in a modified live build.

## Runtime implications

Static structure does not by itself prove load-order precedence, but it materially upgrades the architecture model:

- the parent knows the exact child ARC membership;
- the parent also carries those child resources as first-class entries;
- therefore parent/child synchronization is not merely a filename-duplication coincidence;
- changing a child without considering the parent preload copy can leave two payload variants for the same manifested identity.

This is especially relevant to `cp_name_pl` / `cp_name_nak` nameplate resources.

## External corroboration

The live executable contains reflection/class strings adjacent to `rArchive`:

- `ResourceNum`
- `TotalSize`
- `ResourceList`
- `Resources`
- `rArchive::CompressStream`
- `rArchive::DecompressStream`
- `rArchive`

Public MT Framework type databases independently identify `0x73850D05` as `rArchive`.

No public SCRA parser was found in REvilLib/Kuriimu2/MT-Framework-Tool/umvc3-tools during this pass; this document therefore records a live-Utage-derived structure.

## Evidence level

- SCRA binary structure: **STRUCTURALLY VERIFIED**
- 117/117 child-manifest equivalence: **STRUCTURALLY VERIFIED**
- parent contains 507/507 manifested identities: **STRUCTURALLY VERIFIED**
- preload/runtime precedence interpretation: **SUPPORTED**, pending controlled runtime test where required


## Reference graph and deduplication

The SCRA relation is a graph, not necessarily a contiguous block delimiter.

Observed parent statistics:

| Parent | SCRA manifests | Pair references | Unique referenced resources | Reused references | Parent-only resources |
|---|---:|---:|---:|---:|---:|
| `title_id.arc` | 31 | 123 | 112 | 11 | 39 |
| `quest_id.arc` | 31 | 274 | 172 | 102 | 2 |
| `tenka/friend.arc` | 55 | 110 | 110 | 0 | 0 |

`friend.arc` happens to store each child group's resources contiguously before its SCRA descriptor (55/55).

That is **not** a general rule:
- `title_id.arc`: 20/31 manifests matched the immediately preceding N entries;
- `quest_id.arc`: 7/31 did.

The reason is resource reuse/deduplication and parent-only resident resources. A parser must resolve SCRA pairs by identity, not by positional adjacency.

Notable shared resources in `quest_id.arc` are `nakama_*` and `cp_name_nak_*` textures referenced by up to four child manifests.

## Cross-route dependency proof

`rom/eng/tenka/friend.arc` contains 55 SCRA manifests whose child paths are explicitly under:

`rom/jpn/pause/friend_*`

and every referenced JPN child ARC exists and matches its manifest.

This is structural proof that an ENG-route parent can intentionally depend on resources located under `rom/jpn`. Folder language labels therefore cannot be treated as a simple live/dead routing boundary.

## Practical ownership rule

For an SCRA-backed family, model:

`parent resident pool <-> SCRA child membership graph <-> physical child ARC(s)`

rather than assuming either:
- the child ARC is the only owner, or
- the parent is merely a duplicate cache.

Static SCRA evidence proves membership and resident duplication. Runtime precedence between parent and child still requires runtime/load evidence for the specific family.
