# Public Technical Canon

This document contains concise public-safe facts that currently have enough project evidence to guide engineering. Scope matters: a fact proven for one family/fixture must not be silently generalized to every MT Framework resource.

## Platform and container family

- Target: **Sengoku BASARA 3 Utage**, PlayStation 3 (BLJM60389).
- Engine family: **MT Framework Lite**.
- Certified Utage ARC path uses PS3 big-endian ARC v8 with on-disk magic `\0CRA`.
- The current certified ARC reader/writer uses **80-byte table entries**.
- Preserve member names/order/type hashes/flags and untouched stored payloads where the transaction supports byte identity.
- Unknown/non-certified compression, unexplained non-zero structural bytes, or unsupported archive features must fail closed rather than be guessed.


### ARC entry size/flag packing

Independent public implementations now strongly corroborate the PS3/big-endian ARC member word at entry offset `0x48` as **29 bits of decompressed size plus 3 low flag bits**.

- REvilLib models this as `ARCFileSize = Size(29) + Flags(3)`.
- Kuriimu2 big-endian ARC handling reads decompressed size as `DecompSize >> 3` and writes it as `(oldLow3Bits) | (size << 3)`.
- An older PS3 MT Framework repacker independently reads `size = word >> 3` and writes `(size << 3) | 0x2`.
- REvilLib initializes new entries with flag value `2`.

The **structural packing is strongly corroborated**. The semantic meaning of individual low-bit values is not yet proven for Utage, so those bits are protected metadata: preserve the original low 3 bits for existing entries unless a controlled test proves a required change.


### MT Framework V2 resource-class hashes

For the SB3 / Samurai Heroes ARC family, the newer resource-class hash used in ARC entries is externally corroborated as an MT Framework V2 CRC32B-derived hash:

`hash = (~CRC32(class_name_bytes)) & 0x7FFFFFFF`

Known vectors:

- `rTexture -> 0x241F5DEB`
- `rMessage -> 0x10C460E6`
- `rLayoutSpr -> 0x60DD1B16`
- `rArchive -> 0x73850D05`

This permits candidate class names to be tested programmatically instead of treating every unknown ARC type hash as opaque. It does **not** reverse a hash to a unique class name; candidate naming still requires evidence.

Public helper: `project/Foundry/tools/mt_hash.py`.

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


### PS3 block-compressed colour-order transform

The historically proven Kuriimu2 revision used by this project applies `BcSwizzle` to PS3 block-compressed textures before BC encoding/after BC decoding.

That transform is generated from bit coordinates:

`[(1,0), (2,0), (0,1), (0,2)]`

which defines a **4x4 Morton/Z-order colour microtile**. It is applied to the decoded colour stream used to form 4x4 BC blocks, not as a generic post-encode "8x4 BC block" shuffle.

Therefore the old broad rule that PS3 BC texture safety can be described as an 8x4-block tile is superseded. For certified production, use the exact proven Kuriimu transform or fixture-derived equivalent rather than a guessed RSX tile size.

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


## Observed Utage TEX/XET format population

**Evidence level: STRUCTURALLY VERIFIED by a live ARC-corpus census (2026-09-25).**

Every `rTexture` entry in the current ENG/JPN routes was inspected far enough to parse its XET header.

ENG corpus:
- 50,342 texture entries / 50,342 valid XET headers
- 0x2A: 49,793
- 0x17: 419
- 0x19: 75
- 0x15: 36
- 0x27: 19
- 0x2B: **0**

JPN corpus:
- 47,458 texture entries / 47,458 valid XET headers
- 0x2A: 47,037
- 0x17: 320
- 0x19: 50
- 0x15: 36
- 0x27: 15
- 0x2B: **0**

Across 97,800 current-route texture entries, no 0x2B fixture was found. RBxG/0x2B remains useful MT Framework cross-game knowledge, but it is not an observed Utage production format and should not drive Utage-specific engineering unless a real Utage fixture appears.


## Utage resource-class universe

**Evidence level: STRUCTURALLY VERIFIED against the current JPN ARC corpus and externally cross-resolved with REvilLib's SB3 PS3 class database (2026-09-25).**

The current JPN route contains 48 distinct ARC type hashes. All **48/48** resolve to classes present in REvilLib's original Sengoku BASARA 3 PS3 profile. No live Utage class hash requires a Samurai Heroes-only class definition.

39/48 are shared by SB3 and Samurai Heroes. Nine live classes are present in SB3 but absent from REvilLib's Samurai Heroes profile:

- `0x7DC513BA` rQuestInfo / qif
- `0x494CE020` rRewardDrop / rew
- `0x23DBF8CE` rBasaraShop / bsh
- `0x1DA0352D` rTenkaPlInfo / tpi
- `0x5B99F299` rTenkaUnlock / tul
- `0x4CD902BC` rVersusPlayerInfo / vpi
- `0x314ACB2A` rVersus30Player / v30
- `0x0C103FAA` rFieldInfo / fif
- `0x1ACCC2DD` rEvtParam / etp

Use the type hash/class mapping as stronger format identity evidence than a suggestive directory name.
