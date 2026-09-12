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

Exact PSL/LSP geometry is **not** claimed yet. Foundry may expose known controller/node references, but geometry stays `Unknown` until proven by a parser/fixture.

## Design rules

- Proven game data beats guesses.
- `Can read` does not mean `safe to write`.
- AI can propose; it never owns project truth or approval.
- Production artwork cannot modify pixels outside approved edit masks.
- Desktop fonts are mockup-only unless a style has been explicitly approved; official SH/game glyph sources outrank font imitation.
- Every bug that teaches us a format rule should become a regression fixture.
- Alrummi remains untouched and acts as a knowledge/fixture source.

## Repository layout

- `src/BasaraFoundry.Domain` — durable project contracts and safety states.
- `src/BasaraFoundry.Game.Utage` — Utage-specific format adapters.
- `src/BasaraFoundry.App` — WinUI 3 shell; no binary-format logic.
- `tests/BasaraFoundry.SmokeTests` — dependency-light regression/smoke tests.
- `schemas` — authoritative text schemas for portable project state.
- `docs` — product contract and research notes.

## Technology baseline

- .NET 10
- Windows x64 first
- WinUI 3 / Windows App SDK stable channel
- Authoritative project state in normal files; caches are disposable

Current development branch: `foundry-v0.1`.
