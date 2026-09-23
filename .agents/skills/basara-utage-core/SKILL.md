> **2026-09-23 SUPERSESSION — READ FIRST**
>
> Current startup is: BASARA Foundry Master Index -> **00 RELEASE COMPLETION GATE — 100% ENGLISH + HIGH-QUALITY TEXTURES — 2026-09-23** -> **00 FRESH CHAT HANDOFF — 2026-09-23 LATE — READ THIS FIRST (SUPERSEDES 21-00)** -> current task evidence.
>
> Runtime ownership is now proven as load-family + exact typed/path resource identity under **first successful population claim wins**. Use the current **Resource Ownership Analyzer** instead of inferring provider precedence from filenames or filesystem order. Use **Utage Donor Matcher V5.1** before manual Samurai Heroes donor hunting. rom/jpn is **not reliably pristine Japanese** and cannot decide donor direction by hash equality. Current live E: bytes remain production authority.
>

---
name: basara-utage-core
description: Core operating procedure for the Sengoku BASARA 3 Utage PS3 English localisation project and BASARA Foundry. Use for any Utage engineering, patch continuation, ARC ownership/routing, source-of-truth recovery, project handoff, or when deciding which more specific BASARA skill applies.
---

# BASARA Utage Core Engineering

This skill is the front door for the Sengoku BASARA 3 Utage PS3 English patch and BASARA Foundry.

The user's explicit instructions take precedence over this skill. Do not use this skill to add unnecessary confirmation gates or to defer work that can be completed safely.

## Mandatory startup

Before substantial Utage engineering:

1. Recover the current project state instead of starting from generic MT Framework knowledge.
2. Treat Google Drive `BASARA Foundry` as the canonical engineering memory and the GitHub repository as the canonical code history.
3. Read, in order when available:
   - `00 READ ME FIRST — BASARA FOUNDRY / UTAGE MASTER SOURCE OF TRUTH`
   - `01 UTAGE TECHNICAL CANON — FORMATS, ROUTING, WORKFLOW, PROVEN FAILURES`
   - the most relevant current checkpoint/handover for the task
4. Verify the latest source/master before mutating an ARC or project file. Never silently patch an older copy when a newer live baseline exists.
5. Reuse existing manifests, fixture results, audits, and Foundry code before rescanning or rediscovering the project.

## Project identity

- Game: Sengoku BASARA 3 Utage
- Platform: PlayStation 3
- Engine: MT Framework Lite
- Primary patch route: current Utage English route under the patched `/eng` architecture
- Archive family: PS3 big-endian ARC v8 (`\0CRA` on disk)
- Texture family: PS3 MT Framework TEX/XET (`\0XET` on disk), including v0x97 fixtures
- Layout family: PSL/LSP; treat field semantics as fixture-specific until proven

## Transaction discipline

Treat substantial work as a checkpointed engineering transaction:

- narrow scope
- deterministic inputs
- source hashes when practical
- explicit output path
- sibling/rebuilt outputs instead of destructive in-place edits
- verification before promotion
- preserve an audit/handover for discoveries that change project canon

Do not mix research claims, synthetic assumptions, and fixture-proven facts without labels.

## Ownership before editing

Never treat a matching filename as proof of ownership.

For any resource change, resolve the actual runtime owner chain as far as the task requires:

`runtime screen/state -> owning ARC -> controller/layout -> member/resource -> texture/message/layout object`

For shared resources, identify every runtime owner that must receive the synchronized final resource. A successful one-ARC patch is not complete when the resource has multiple live owners.

## Source preservation rules

- Canonical source ARCs are immutable inputs.
- Production outputs are sibling/build ARCs.
- Preserve unrelated ARC members, metadata, ordering, flags, and stored payloads unless a separately proven transformation requires otherwise.
- Fail closed on unexplained non-zero archive structure, unsupported compression, unsupported texture layouts, ambiguous owners, or unknown write semantics.
- Never transplant a whole matching-name resource from another BASARA game merely because the name matches.

## Artwork approval rule

For texture/UI artwork changes:

1. Show the generated/rebuilt candidate artwork first.
2. Where possible show an in-layout/in-game mockup using the owning controller/layout.
3. Let the user judge scale, placement, cropping, readability, and style.
4. Only then perform the actual XET/TEX and ARC rebuild.

A PNG is not completion of an ARC texture job.

Completion means the approved artwork has been converted through the certified texture path, inserted into the owning ARC(s), verified, and returned/deployed as the rebuilt game asset.

## Routing to other BASARA skills

Use `basara-utage-texture-engineering` whenever the task involves:

- TEX/XET
- BC1/BC3
- RBxG / format 0x2B
- texture atlases
- title/gallery/panel/UI textures
- LSP/PSL-driven texture presentation
- texture replacement or ARC repacking

Use `basara-utage-research` whenever the task involves:

- reverse-engineering an unknown field/format
- comparing public MT Framework tools or other BASARA games
- testing a hypothesis
- recording evidence levels
- forensic audits
- DeepSeek/Claude/external-agent research handoffs
- updating technical canon from new evidence

Use both when research directly affects a production texture/layout pipeline.

## Evidence hierarchy

Prefer evidence in this order:

1. real Utage runtime result tied to exact build/hash
2. real Utage fixture with deterministic parser/test
3. shipped Foundry regression using real/derived fixture
4. public PS3 MT Framework source/tool directly matching the code path
5. another BASARA/MT Framework title on the same platform
6. synthetic test
7. hypothesis

Never promote a generic table over contradictory real Utage evidence without resolving the contradiction.

## Standing proven/safety rules

- ARC v8 PS3 table entries are 80 bytes in the current certified reader/writer path.
- PS3 ARC/XET structures are big-endian in the certified Utage path.
- XET swizzle must not be guessed. `swizzle != 0` is fail-closed unless a fixture-specific writer exists.
- Multi-mip or unexplained trailing XET data is fail-closed unless a certified writer handles the full resource.
- BC-compressed edits operate on legal 4x4 blocks; untouched certified blocks should remain byte-identical where the graft path guarantees this.
- The historical blanket 8x4/32x16 PS3 swizzle theory is not canon. Do not reintroduce it without actual Utage evidence.
- The empirical LSP 2x scale relationship is useful for known fixtures, not a universal parser rule.
- User-visible software approval is not the same as human artwork approval. Internal verification may make an asset eligible for review; it does not substitute for the user's visual sign-off.

## Do not regress these project lessons

Do not:

- return only an image when asked to patch an ARC
- rediscover known ARC/XET fundamentals from scratch
- call speculative offsets proven
- use a pristine Japanese texture as the normal base for an incremental English edit
- overwrite pre-existing English artwork outside the approved edit
- flatten special PS3 texture channel semantics into ordinary RGBA without proof
- treat a synthetic writer/reader roundtrip as proof of Capcom's real format
- modify canonical source files in place

## Current code-state caveat

The authoritative implementation may be ahead of this skill document. Before a production change, inspect the current `foundry-v0.1` branch and any open hardening PR/checkpoint. If code and this skill disagree, preserve safety, investigate the newer evidence, and update the skill/canon rather than silently following stale text.
