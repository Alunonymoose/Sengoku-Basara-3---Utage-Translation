# BASARA Foundry

BASARA Foundry is a fresh, Utage-first translation workstation. It is intentionally **not** an Alrummi GUI rewrite.

## v0.1 vertical slice

The first milestone proves one complete safe workflow:

1. Identify/open a real Utage asset.
2. Show Japanese, current English, Samurai Heroes reference, working candidate, and encoded result.
3. Preserve canonical source trees as read-only inputs.
4. Enforce explicit editable regions and approval state.
5. Rebuild only verified resources while preserving unrelated archive members.
6. Attach runtime evidence before an asset can become `RuntimeVerified`.

Exact PSL/LSP geometry is **not** claimed generically. Foundry may expose fixture-proven controller/node references, but geometry stays `Unknown` until proven for that exact layout family/fixture. A generic certified PSL/LSP writer is not part of v0.1.

## Hardened TEX/XET production rules

- **Normal incremental localisation uses the current live target XET payload as its preservation base.** Only BC blocks intersecting the explicit approved edit mask may be replaced. This prevents a new edit from reverting existing English work elsewhere in the same atlas.
- Pristine Utage/JPN XETs remain mandatory compatibility/reference evidence where available, but their payload is used as the untouched-art base only in an explicit `PristineRestore` repair transaction.
- Candidate differences in completely untouched BC blocks are ignored because those blocks are copied byte-for-byte from the selected graft base. Candidate changes outside the exact edit mask **inside a touched 4×4 BC block** fail closed.
- The selected live target XET always owns the output shell/container. Donor-whole-XET transplantation is forbidden.
- Format `0x15` remains ambiguous and is not decoded/written through a guessed BC2/BC3 path.
- Format `0x2B` uses BC3 storage with PS3 RBxG artist-channel semantics. Plain RGBA writing is refused. `UtageRbxgCodec` provides the explicit stored-channel ↔ base/mask transform; generic production grafting remains fail-closed until the dedicated RBxG path is fixture-proven.
- Non-zero XET swizzle, multi-mip/trailing-data writes, and unsupported format families remain fail-closed.
- ARC rebuilds preserve protected entry metadata and untouched stored payloads. Unexplained non-zero bytes in inter-member gaps or after the final member cause a hard refusal instead of being silently discarded; zero trailer length is preserved.
- Software verification never substitutes for final human review of the encoded texture extracted from the built sibling ARC, nor for exact-build runtime evidence.

## Design rules

- Proven game data beats guesses.
- `Can read` does not mean `safe to write`.
- AI can propose; it never owns project truth or approval.
- Production artwork cannot modify unapproved pixels inside touched compression blocks.
- Unrelated live atlas blocks and unrelated ARC members must survive byte-for-byte where the certified path says they are untouched.
- Desktop fonts are mockup-only unless a style has been explicitly approved; official SH/game glyph sources outrank font imitation.
- Every bug that teaches us a format rule should become a regression fixture.
- Alrummi remains untouched and acts as a knowledge/fixture source.

## Repository layout

- `src/BasaraFoundry.Domain` — durable project contracts and safety states.
- `src/BasaraFoundry.Game.Utage` — Utage-specific format adapters.
- `src/BasaraFoundry.App` — WinUI 3 shell; no binary-format logic.
- `tests/BasaraFoundry.SmokeTests` — dependency-light regression/smoke tests.
- `tests/BasaraFoundry.GraftSmokeTests` — target-shell, incremental-preservation, RBxG, shared-owner, and ARC graft safety regressions.
- `schemas` — authoritative text schemas for portable project state.
- `docs` — product contract and research notes.

## Technology baseline

- .NET 10
- Windows x64 first
- WinUI 3 / Windows App SDK stable channel
- Authoritative project state in normal files; caches are disposable

Current development branch: `foundry-v0.1`.
