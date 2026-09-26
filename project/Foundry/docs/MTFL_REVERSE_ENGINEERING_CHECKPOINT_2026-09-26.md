# MT Framework Lite / BASARA executable reverse-engineering checkpoint — 2026-09-26

## Scope

Static comparison of decrypted PlayStation 3 executables from **Sengoku BASARA: Samurai Heroes** and **Sengoku BASARA 3 Utage**. This note records reusable architecture findings only; no retail executable or asset payloads are redistributed.

## Evidence identity

Compared executable sizes:
- Samurai Heroes: 15,603,808 bytes
- Utage: 17,440,144 bytes

Reference SHA-256:
- SH: `b610d0b0c4a4341454fe6c0800ba4d1843b6ecba7e40aedfab366ddab4d59f0b`
- Utage: `a3cafcb5656a0d6ec7bdf9f2a273cb494e3e195950dd06b2c1d19ff97a43b99b`

## Shared PPU codebase

Using PS3 PPU function descriptors:
- SH exposes approximately 36,328 unique function entry points.
- Utage exposes approximately 38,602.
- At least 8,279 functions are byte-identical before relocation/TOC/branch normalization.

This is a conservative lower bound and strongly supports cross-build function matching as a reverse-engineering strategy.

## Six-way language directory resolver

A homologous function exists in both builds:

- SH function entry: `0x000891D4`
- Utage function entry: `0x000919F4`

Observed behaviour:
- reads the language/index state at object offset `+0x24`;
- bounds-checks it against six cases;
- dispatches through six cases;
- returns a global directory string.

Resolved mappings:

| Index | Samurai Heroes | Utage |
|---:|---|---|
| 0 | `jpn` | `eng` |
| 1 | `eng` | `eng` |
| 2 | `fre` | `fre` |
| 3 | `spa` | `spa` |
| 4 | `ger` | `ger` |
| 5 | `ita` | `ita` |

**Finding:** Utage retains the six-language resolver, but its Japanese/default slot is redirected from `jpn` to `eng`.

This helps explain the observed coexistence of physical ENG package routing with logical JPN resource namespaces.

Evidence level: **STRUCTURALLY VERIFIED**.

## Resolver vocabulary

Both executables expose localisation/resource-routing identifiers including:
- `mLanguage`
- `sBasaraLayout`
- `id\lsp\jpn`
- `id\lsp\abr`
- `id\mod\jpn`
- `id\texture\jpn`
- `id\lsp\com`
- `id\mod\com`
- language-dependent templates for `shogo`, `waza`, `army`, `name`, `cp_face_msg`, `nakama`, `cp_name_pl`, and `cp_name_nak`.

Samurai Heroes exposes Western texture roots including ENG/GER/FRE/SPA/ITA/DUT. Utage exposes KOR/TWN/ENG while retaining the `id\lsp\abr` identifier in executable data.

The presence of a string alone does not prove a resource family is active; runtime reachability remains a separate question.

## Generic resource hierarchy

The executables expose generic MT Framework resource classes and member names.

### `cResource`

Observed member-name metadata:
- `mPath`
- `mID`
- `mRefCount`
- `mSize`
- `mAttr`
- `mTag`
- `mState`
- `mQuality`

### `rArchive`

Observed archive/resource metadata:
- `ResourceNum`
- `TotalSize`
- `ResourceList`
- `Resources`
- `rArchive::CompressStream`
- `rArchive::DecompressStream`
- `rArchive`

The observed `rArchive` factory allocates `0x70` bytes and clears four archive-specific words at approximately `+0x60`, `+0x64`, `+0x68`, and `+0x6C`.

The existence of this four-field block is verified. Exact name-to-offset assignment remains provisional pending method-level confirmation.

## Function-descriptor / class-table recovery

PS3 class tables can be followed through PPU function descriptors into executable code.

Observed SH examples:

`cResource`-associated entries:
- `0x00C628C0`
- `0x00C62964`
- `0x00700608`

`rArchive`-associated entries:
- `0x00C62D08`
- `0x00C62DC8`
- `0x00704738`

The `0x00704738` path is the observed `0x70`-byte archive allocation/factory path.

Reusable RE method:

`class/name string -> TOC/global slot -> class table -> PPU function descriptor -> executable code`.

## `sResource`

The executable exposes a higher-level generic resource manager:
- `sResource`
- `sResource::RemoteInfo`
- `sResource::DecompressStream`
- `sResource::TypeInfo`

Associated strings include:
- `BuildResource`
- `Build Archive`
- `arc.xml`
- `Resource Loader`
- `RemotePC`
- `RemoteResourceConvert`
- `mRootDirectory`
- `mResourceFolder`
- `mNativeFolder`
- `mResourcePath`
- `mNativePath`
- `nativeXenon`
- `nativeWii`

This proves substantial MT Framework resource/build abstractions survive in the retail executable. It does **not** prove development/remote/loose-resource paths are reachable in retail.

## `sFile`

Observed filesystem/cache vocabulary includes:
- `sFile`
- `MountPath`
- `cachePrefetch`
- `mCacheEnable`
- `CachePath`
- `mGdataEnable`
- `GdataPath`
- `updateHDDInfo`
- `/dev_bdvd/PS3_GAME/USRDIR`

Current generic stack model:

`PS3 filesystem -> sFile -> sResource -> cResource -> rArchive -> logical resources`

## BASARA loading layer

BASARA-specific loading metadata includes:
- `sLoadControl`
- `sLoadControl::cArcData`
- `sLoadControl::cLoadQue`
- `mLoadRno`
- `mLoadQueId`
- `mLoadQue`
- `mLoadPrio`
- `mArcList`
- `mpActorInfo`
- `mLoadStatus`

Current bounded model:

`mLanguage -> language-directory resolver -> path formatting -> sLoadControl -> cLoadQue/cArcData -> sResource/rArchive`

Do not generalize `sLoadControl` as universal MT Framework infrastructure without cross-title evidence.

## Source breadcrumbs

Retail executable strings include source-path/assertion breadcrumbs such as:
- `../MT/MtSynchronize.h:35`
- `../MT/MtSynchronize.h:49`
- `../../MT/MtSynchronize.h:35`
- `../../MT/MtSynchronize.h:49`

These are useful anchors for recovering original engine module boundaries.

## Next reverse-engineering target

Trace:

`sLoadControl::cArcData -> rArchive load -> sResource registration -> cResource state/refcount -> ResourceList insert/remove`

Primary unresolved question:

**What exactly happens when two loaded ARCs expose the same logical resource key?**

The answer should clarify duplicate-provider precedence, resident package shadowing, unload/refcount behaviour, and previously observed first-successful-population behaviour.

## Guardrails

- String presence is not runtime reachability.
- Member names are not exact field types/offsets until code confirms them.
- Dormant build/remote tooling is not assumed usable.
- BASARA-layer behaviour is not promoted as universal MT Framework behaviour without cross-title evidence.
- Address claims remain tied to the executable hashes above.
