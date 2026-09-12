# Architecture — v0.1

## Boundary rule

`BasaraFoundry.App` must never parse or rebuild game binaries directly. UI state calls domain/application services; Utage binary knowledge lives under `BasaraFoundry.Game.Utage` and must be fixture-tested.

## Source of truth

Canonical game trees are read-only. Foundry project truth is ordinary versionable files (JSON, approved artwork, recipes, evidence). Any SQLite database introduced later is a rebuildable cache, never the sole copy of project state.

## Capability model

A handler reports independent levels for `Read`, `Write`, `RoundTrip`, and `Runtime`. Opening a format does not grant write permission. Production actions require the capability demanded by that action.

## Utage v0.1 format policy

The first ARC adapter certifies only the PS3 big-endian `\\0CRA` v8 form. Other MT Framework variants remain unsupported until a fixture proves them. This is deliberately narrower than Alrummi's broad inspection support.

## UI policy

Normal mode talks in screens/assets/reviews/builds rather than ARC offsets. Engineering details remain available but secondary.

The first asset workspace shows five truths side-by-side:

- Original Japanese
- Current English
- Samurai Heroes
- Working candidate
- Encoded game-format result

Exact PSL/LSP geometry is not claimed yet. Known controller/node relationships may be shown with geometry explicitly marked `Unknown`.

## Art policy

Production changes are mask-scoped. Pixels outside approved masks must remain identical. Whole-texture automatic polishing is forbidden in production mode.

Typography priority:

1. Exact official Samurai Heroes pixels/assets.
2. Real game glyph/font providers.
3. Foundry BASARA Style Kits built from approved official/verified samples.
4. Desktop fonts only for mockups unless explicitly approved.
5. AI proposals are candidates, never project truth.

## Alrummi relationship

Alrummi remains untouched. Proven discoveries, fixture cases and algorithms may be ported only behind Foundry interfaces and tests. The Tk GUI/state architecture is not carried forward.

## Crash/recovery direction

Risky indexing and format work will move behind a worker-process boundary. Writes will use temporary outputs followed by validation and atomic promotion. This is a v0.1 implementation target after the core reader/tests are green.
