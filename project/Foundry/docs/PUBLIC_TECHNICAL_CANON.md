# Public Technical Canon

This document contains concise public-safe facts that currently have enough project evidence to guide engineering. Scope matters: a fact proven for one family/fixture must not be silently generalized to every MT Framework resource.

## Platform and container family

- Target: **Sengoku BASARA 3 Utage**, PlayStation 3 (BLJM60389).
- Engine family: **MT Framework Lite**.
- Certified Utage ARC path uses PS3 big-endian ARC v8 with on-disk magic `\0CRA`.
- The current certified ARC reader/writer uses **80-byte table entries**.
- Preserve member names/order/type hashes/flags and untouched stored payloads where the transaction supports byte identity.
- Unknown/non-certified compression, unexplained non-zero structural bytes, or unsupported archive features must fail closed rather than be guessed.

## TEX/XET

- PS3 texture resources use the MT Framework `\0XET` family; the historical Exient/XGS interpretation was wrong.
- Known v0x97 resources use a 20-byte header, but dimensions/orientation remain family/fixture claims rather than a universal assumption.
- BC-compressed edits operate on independent 4x4 blocks.
- Do not invent swizzle/tile behaviour from generic PS3 lore when a real Utage fixture is available.

### Format 0x2A

Current project evidence treats 0x2A as BC3 storage plus the Kuriimu2 PS3 YCbCr colour transform.

From normal display RGBA to stored channels:

```text
Y  = 0.299R + 0.587G + 0.114B
Cb = 123 - 0.168736R - 0.331264G + 0.5B
Cr = 123 + 0.5R - 0.418688G - 0.081312B
stored = (Cr, inputAlpha, Cb, Y)
```

Read transform:

```text
alpha = G
Y  = A
Cb = B - 123
Cr = R - 123
outR = clamp(Y + 1.402*Cr)
outG = clamp(Y - 0.344136*Cb - 0.714136*Cr)
outB = clamp(Y + 1.772*Cb)
```

PS3 BC1/BC2/BC3 RGB565 colour endpoints are big-endian u16 in the certified project path; index/alpha packing remains standard.

### Format 0x2B / RBxG

Do not expose 0x2B as ordinary one-plane artist RGBA.

Project representation:

```text
base = (A,A,A,G)
mask = (R,B,0,255)
stored = (mask.R, base.A, mask.G, base.G)
```

This preserves hidden R/B information. Generic one-PNG RGBA writes remain unsafe unless newer real-fixture evidence supersedes this rule.

### Format 0x15

Current project evidence supports BC2/DXT3 read/preview for known fixtures. Production writing requires a real edit/rebuild/runtime fixture before promotion.

## Atlas/layout discipline

- The historical 2x logical-to-atlas relationship is useful for known fixtures, not a universal LSP/PSL parser rule.
- Custom atlas work must be **candidate first, mockup second**.
- Preserve exact source dimensions, slot coordinates, padding/material fields, alpha/channel semantics and untouched pixels/blocks.
- A generated whole-screen concept is not a production atlas.

## Runtime ownership

Containment is not authority.

Use the strongest available chain:

`screen/state -> consumer/controller/layout -> typed/path resource identity -> loaded package family -> registration/preload behaviour -> visible result`

Project evidence supports first-successful-population precedence for tested resource families. Keep the claim bounded to the tested family/load conditions; do not turn it into a universal engine law without evidence.

A duplicate path in several ARCs proves presence only. Shared intended-equivalent providers should be synchronized when evidence shows they form one runtime family.

## Samurai Heroes donor use

Samurai Heroes is the preferred official English localisation reference where compatible, but matching names are not enough.

For a donor, verify the relevant combination of:

- content role;
- dimensions/format/channel semantics;
- layout/source rectangle;
- companion LSP/PSL/text/display data;
- runtime owner family.

## Source authority

For production mutation, fresh current user-supplied/live bytes win over historical backups, Drive snapshots, old checkpoints or embedded indexes.

Public maps and prior hashes are navigation/evidence. They are not a substitute for the current binary being modified.

## Runtime captures

RPCS3 RSX/RRC captures are runtime memory/state evidence, not filesystem metadata. A command-referenced payload can prove runtime byte participation; original ARC/path ownership still requires correlation with live resources and load/precedence evidence.

## Evidence vocabulary

Use:

- **HYPOTHESIS**
- **STRUCTURALLY VERIFIED**
- **VISUALLY VERIFIED**
- **RUNTIME OBSERVED**
- **RUNTIME PROVEN**

Keep static correctness separate from runtime ownership or visual acceptance.


## ARCS / SCRA child-archive manifests

**Evidence level: STRUCTURALLY VERIFIED on the current Utage ENG and JPN ARC corpora (2026-09-25).**

MT Framework `rArchive` resources (class hash `0x73850D05`) inside three Utage parent families are not embedded ARC containers. Their raw payloads use the PS3 on-disk bytes `SCRA`; REvilLib independently recognizes the corresponding FourCC as `ARCS`.

Observed binary layout:

```text
offset  size  meaning
0x00    4     magic: SCRA on PS3 disk / ARCS logical FourCC
0x04    2     big-endian ARC version (0x0008 in Utage)
0x06    2     child member count N
0x08    N*8   repeated:
                 u32 BE resource class/type hash
                 u32 BE full lowercase-path hash
```

For the second field of each pair:

```text
path_hash = (~crc32(lowercase(internal_resource_path))) & 0xffffffff
```

This deliberately differs from the common MT Framework V2 class hash helper, which masks the high bit to `0x7fffffff`.

Current live corpus:

- ENG: 117 `rArchive` entries; all 117 raw; all 117 decode as ARCS/SCRA.
- JPN: 117 `rArchive` entries; all 117 raw; all 117 decode as ARCS/SCRA.
- Families per route: 31 pl-face child manifests, 31 quest child manifests, 55 friend/pause child manifests.
- Each route contains 507 child-member references.
- 507/507 references resolve uniquely to a flattened resource in the containing parent ARC.
- 117/117 manifest tables exactly match the ordered member identity table of the corresponding standalone child ARC.

Therefore the supported structural model is:

```text
parent ARC
  = flattened child resource payloads
  + ARCS/SCRA virtual child-archive records
  + optional parent-only resources
```

The parent may deduplicate resources shared by multiple child manifests. A manifest references resources by class + lowercase-path hash, not by adjacency or payload offset.

Payload identity is independent of manifest identity. In pristine/current JPN parent families, the flattened payloads match standalone child payloads exactly. In the current localized ENG tree, some parent flattened resources intentionally/temporally diverge from standalone child ARC payloads while the ARCS/SCRA manifest remains identical. Do not infer payload equality from matching manifest identity.

This proves the serialization/topology contract, not by itself runtime precedence. Runtime ownership still requires load/registration/runtime evidence.
