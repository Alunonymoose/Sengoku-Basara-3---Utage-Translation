# Style-kit assembler applied (2026-09-12)

## Source

DeepSeek resubmit against the Foundry assistant pack, after Grok scrutiny of parallel-API / hollow style-kit failures.

## What landed on `foundry-v0.1`

| Path | Role |
|------|------|
| `src/BasaraFoundry.Game.Utage/Art/IStyleKitV0.cs` | Coverage + palette contract |
| `src/BasaraFoundry.Game.Utage/Art/StyleKitV0Compositor.cs` | Stroke / fill / bevel pixel ops |
| `src/BasaraFoundry.Game.Utage/Art/SyntheticStyleKitV0.cs` | CI 5×7 bitmap kit |
| `src/BasaraFoundry.Game.Utage/Art/UtageStyleKitAssembler.cs` | Assemble → candidateRgba + mask01 |
| `tests/BasaraFoundry.StyleKitSmokeTests/` | Console smoke + real `BuildSibling` |
| `docs/STYLE_KIT_ASSEMBLER.md` | Honest v0 docs |
| `.github-ci-fragment-stylekit.yml` | CI step fragment |

## Corrections applied vs DeepSeek draft

1. Fixtures copied from `GraftSmokeTests` (`BuildXetFromRgba`, `BuildSingleEntryArc`).
2. `tx.SiblingArcBytes` (not `SiblingArc`).
3. Multi-line asserts use vertical extent (`minY`/`maxY`), not row 0/31.
4. SH confidence documented as App adapter over `TryResolveUniqueStrong`.
5. Tier highest-wins (`MockupBlocked` → `StyleKitV0` → `ShPixelCrop`).

## Score honesty

- **~7.5** if smoke is green: mask-safe, real compositor, production path unchanged.
- **Not 9+**: synthetic 5×7 only; no App wire; no end-to-end SH unique-strong proof.

## Local verify

```bash
cd project/Foundry
dotnet run --project tests/BasaraFoundry.StyleKitSmokeTests/BasaraFoundry.StyleKitSmokeTests.csproj -c Release
```
