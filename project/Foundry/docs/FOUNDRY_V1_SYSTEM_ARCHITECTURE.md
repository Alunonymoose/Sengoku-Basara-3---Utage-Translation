# BASARA Foundry v1 — Whole-project system architecture

Status: implementation contract, 2026-09-17.

## Mission

Foundry must become the single Utage workbench for understanding, modifying, verifying and runtime-testing the English patch. It must not be a texture utility with unrelated scripts around it.

The core transaction is:

`game root -> archive/resource census -> dependency graph -> inspect/compare -> guarded edit -> deterministic rebuild -> structural verification -> RPCS3 runtime trace -> evidence promotion`

Every stage emits normal files and hashes. Unknown formats remain visible and immutable until proved.

## 1. Project workspace and source identities

A project stores logical roots, not fragile absolute paths:

- current/live Utage root
- pristine Utage JP root
- official Samurai Heroes ENG root
- optional SB3 JP and Sumeragi reference roots
- RPCS3 executable/config/log locations
- output/evidence root

Each indexed file gets SHA-256, size, logical route, source-role and scan timestamp. A write transaction freezes the exact input hashes before editing.

## 2. ARC subsystem

### Required

- ARC v8 big-endian reader/writer
- extract one/all members without losing type hash, order, flags or stored bytes
- deterministic member manifest
- compressed + raw hash for every member
- reinsert by stable identity `(name,type,index/source archive)`
- diff archive-to-archive at compressed and decompressed levels
- duplicate-name/type detection
- shared-owner search across the indexed game
- unknown/special raw entry support
- sibling output only by default

### UI

Opening an ARC shows a resource table with:

`index | path | type hash | detected magic | kind | compression | raw size | SHA | read capability | write capability | owners/consumers | runtime-seen`

Unknown entries are first-class rows, never hidden.

## 3. Resource registry

Classification uses both declared ARC type hash and decompressed content magic. Magic is authoritative for identification; disagreement is surfaced as evidence.

Initial families:

- `\0XET` texture
- `\0PSL` LSP/PSL layout/controller
- `\0TNF` font/glyph map
- `\0GSM` message strings/control units
- `\0FIM` message format/map records
- `\0CSA` character-set sidecar
- loose `.tex` XET-family resources
- all unknown hashes/magics retained as binary resources

Every format adapter declares capabilities separately:

`IdentifyOnly`, `Read`, `ReadAndPreview`, `ReadAndWriteGuarded`.

Readable must never imply writable.

## 4. XET/TEX texture subsystem

One shared codec handles ARC-contained XET and loose TEX/XET-family resources.

Required metadata:

- complete header bitfields
- dimensions/orientation
- image count
- format code and proven BC interpretation
- mip count/offsets/extents
- swizzle state
- payload/trailing regions
- shell hash and payload hash

Required preview channels:

- RGBA
- RGB
- alpha
- individual R/G/B/A
- game-specific material interpretations where proven

Production write rules:

- preserve target shell/container
- fail closed on unsupported swizzle/mips
- exact edit mask
- block-expanded effective mask for BC formats
- untouched compressed blocks preserved byte-for-byte where applicable
- decode final built resource and compare against candidate/pristine
- report compression collateral
- second approval on the final encoded result

Longer term: certify known PS3 tiled/swizzled forms from real fixtures and add full mip-chain writers one format at a time.

## 5. PSL/LSP layout subsystem

Replace generic printable-string scanning with a fixture-backed structured parser.

For proven PSL v0x21/176-byte-node fixtures expose:

- header/group counts
- exact node index/offset
- name and texture table linkage
- position
- destination rectangle/extents
- source/UV rectangle
- colour/material words
- self/parent/child linkage as decoded
- unknown words retained raw

The editor must be field-specific and transactional. It may write only fields certified for the exact layout schema/fixture family. Unproved words stay read-only.

A layout preview renderer should combine the owning XETs with decoded source/destination rectangles. It must show uncertainty when blend/material semantics are not proved.

## 6. Message/font subsystem

Port the proven `mt_arc_explorer.py` model into Foundry and regression-lock it.

Read support:

- TNF glyph map and advances
- GSM rows, offsets, lengths, terminators and code units
- FIM message maps, formats, line/glyph budgets
- CSA words/metadata
- associated numbered XET atlas pages
- contact-sheet rendering from real glyph atlases

Comparison support:

- pristine Utage vs live ENG per index
- cardinality/order guard
- blank/control/sentinel preservation
- speech/control-envelope diff separate from text/glyph payload diff
- FIM display budget mismatch detection
- companion `rom/.../msg` correlation

Write support remains blocked until the deeper control-envelope invariants are proven on real runtime fixtures.

## 7. Dependency and ownership graph

The index builds edges between:

- ARC -> contained resource
- LSP node -> texture resource/path
- GSM/FIM/TNF/CSA -> message bundle family
- font bundle -> numbered XET pages
- duplicate resource -> sibling ARC owners
- route alias -> ENG/JPN physical owner
- runtime log open -> physical ARC/file
- patch transaction -> changed resources
- screenshot/log evidence -> exact output hashes

This graph answers before editing:

- What owns this screen?
- What consumes this texture?
- Is the same resource duplicated elsewhere?
- Which language route actually loaded?
- What changed between pristine/current/SH?
- Has this exact output ever been cold-boot tested?

## 8. RPCS3 integration

Phase A — safe/offline integration (implement first):

- user selects RPCS3 install and game root
- ingest `RPCS3.log`
- parse VFS mounts and `sys_fs_open` attempts/completions
- normalize `/dev_bdvd/PS3_GAME/USRDIR/nativePS3/...` into Foundry logical routes
- filter trace to the current screen/session time window
- highlight indexed assets actually opened
- preserve the entire log hash as runtime evidence

RPCS3 currently writes the Windows log under the emulator's `log` folder; support guidance explicitly asks for the full log after RPCS3 is closed. This is the canonical source rather than copying the GUI log window.

Phase B — process integration:

- launch the configured official RPCS3 executable with a selected game/ELF only through documented/current CLI behavior
- capture process start/stop and exact RPCS3 executable hash/version
- wait for log creation/rotation and ingest it
- never mutate emulator configuration silently

Phase C — test harness:

- named runtime test cases (`title`, `gallery`, `mission m034/pl015`, etc.)
- install candidate into a staging game root, never canonical source
- boot RPCS3
- ingest trace and screenshots supplied/captured through supported means
- promote evidence only when expected owner/path was actually opened

Savestates may accelerate repeatable tests but never substitute for a required cold-boot test.

## 9. Binary research workbench

Unknown resources need productive tooling rather than a dead-end hex viewer:

- hex + ASCII/Shift-JIS/UTF views
- endian-aware integer/float inspector
- structure stride finder
- repeated-record detector
- pointer/offset candidate detector
- diff two/three resources with alignment
- entropy and zero-region map
- magic/signature scan
- cross-corpus clustering by type hash, size, magic and byte similarity
- export a minimal fixture + hypothesis JSON for research

When a hypothesis graduates, it becomes a parser plus regression fixture.

## 10. Comparison views

Every asset should support a four-way comparison where sources exist:

`pristine Utage | current/live ENG | official SH | working candidate`

For binary resources show structural and byte diffs. For textures show pixel/channel/block diffs. For layouts show node/field diffs. For messages show per-row semantic/control diffs.

## 11. Transaction engine

All writers use one transaction contract:

1. resolve current source by fingerprint
2. freeze inputs
3. resolve owners/consumers
4. validate format capability
5. produce candidate
6. approval gate where visual/content judgement is required
7. build sibling output
8. reopen and parse output
9. prove unrelated bytes/resources preserved
10. generate audit JSON
11. final encoded/result review
12. optional staging install
13. runtime evidence
14. promotion

A crash at any point must be resumable from on-disk transaction state.

## 12. UI architecture

Primary screens:

- **Dashboard** — source-root health, outstanding regressions, recent runtime evidence
- **Game Explorer** — tree of files/ARCs with format badges
- **ARC Explorer** — resource table and extraction/replacement tools
- **Texture Lab** — XET metadata, channels, masks, block map, candidate/final comparison
- **Layout Lab** — nodes, texture links, proven geometry and preview
- **Message Lab** — GSM/FIM/TNF/CSA rows and rendered dialogue
- **Dependency Graph** — owner/consumer/duplicate/runtime edges
- **Runtime** — RPCS3 launch/log ingestion, loaded-file timeline, evidence capture
- **Binary Lab** — unknown resource research
- **Transactions** — every generated output, hashes, approvals and rollback path

No format parsing logic belongs in the WinUI code-behind.

## 13. Tests and corpus verification

CI levels:

1. synthetic unit/smoke fixtures
2. committed tiny real-format fixtures where legally/project-appropriate
3. private corpus tests against user-owned roots
4. runtime evidence tests performed locally

Regression gates include:

- ARC round-trip preservation
- target-shell XET preservation
- BC untouched-block preservation
- XET decode parity
- PSL parser record/string-table linkage
- TNF/GSM/FIM/CSA parser bounds and counts
- dialogue structural guard
- RPCS3 log path extraction
- route resolver correctness
- sibling-owner completeness

## 14. Immediate implementation order

P0:

1. resource classifier/registry
2. port TNF/GSM/FIM/CSA readers from `mt_arc_explorer.py`
3. port the structured 176-byte PSL reader and title fixture knowledge
4. RPCS3 log ingestion and runtime-open correlation
5. ARC Explorer UI backed by those adapters
6. unified extraction/export command

P1:

7. dependency graph persistence
8. texture channel/block visualizer
9. four-way comparison workspace
10. message contact-sheet renderer inside Foundry
11. unknown type-hash census across the full root
12. staged-install/runtime-test transactions

P2:

13. certify additional XET swizzle/mip forms
14. complete PSL hierarchy/material semantics
15. guarded message writer after control-envelope proof
16. plugin-style adapters for later BASARA/MT Framework variants

## Rule of completion

A capability is not "done" because Foundry can open a file. It is done when the exact supported scope is documented, the parser is bounds-checked, real fixtures pass, unsupported forms fail closed, edits are reversible/audited, and runtime evidence can be attached to the exact output.