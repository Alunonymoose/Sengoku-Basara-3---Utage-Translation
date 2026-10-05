# ARC Texture Gallery — canonical visual-QA workflow

## Purpose
This is the default tool for requests such as:
- "pull up title.arc and show every texture"
- "display all textures in menu.arc"
- "scan this ARC for Japanese / ugly / broken textures"
- "show me what is actually in this ARC without opening Kuriimu"

Canonical tool:
`E:\BASARA_FOUNDRY_ORCHESTRATION\project\tools\arc_texture_gallery.py`

PowerShell wrapper:
`E:\BASARA_FOUNDRY_ORCHESTRATION\project\tools\Show-ArcTextures.ps1`

The tool is READ-ONLY. It never patches an ARC.

## Non-negotiable display rule
Textures are decoded through the runtime-proven `xet_ps3.decode_display()` path.
For format 0x2A this applies the PS3/Kuriimu YCbCr display transform.
Do not show raw storage channels as though they were in-game colour.

## Normal assistant workflow
When the user asks to display an ARC:
1. Run the gallery tool on the requested live ENG ARC.
2. Read `E:\BASARA_WORK\ARC_TEXTURE_GALLERIES\LATEST.json`.
3. Display every `overview_*.png` sheet in chat.
4. If QA is requested, inspect `qa_priority_*.png` first, then the full overview.
5. Open individual full-resolution PNGs only for textures that need closer inspection.
6. Do not patch anything merely because a heuristic flag exists; flags are triage, not verdicts.

Example:
`powershell -ExecutionPolicy Bypass -File "E:\BASARA_FOUNDRY_ORCHESTRATION\project\tools\Show-ArcTextures.ps1" "versus\menu.arc"`

A bare unique basename such as `title.arc` is accepted.
Ambiguous basenames fail closed and print the candidate paths.

## Generated output
Each run creates:
`E:\BASARA_WORK\ARC_TEXTURE_GALLERIES\<arc>__<timestamp>\`

Contents:
- `textures\` — every decoded texture as full-resolution game-view PNG
- `sheets\overview_*.png` — all textures, compact visual scan
- `sheets\qa_priority_*.png` — heuristic review priority
- `sheets\custom_english_*.png` — custom/non-SH English assets
- `index.html` — clickable browser gallery with filters and background toggles
- `manifest.json` — hashes, dimensions, format, JPN/SH comparison and artifact metrics

## Comparison / QA fields
The gallery compares each live texture against:
- the same-path Utage JPN ARC, when available;
- the Samurai Heroes donor index by resource basename.

Useful states:
- `JPN exact` — live payload is byte-identical to Utage JPN; inspect if the art contains language.
- `JPN different` — live asset has been changed from JPN.
- `SH exact` — byte-identical to an official Samurai Heroes English donor.
- `CUSTOM_OR_UTAGE` — differs from JPN and has no exact SH donor; visually important.
- `EDGE_TOUCH` / `TINY_COMPONENTS` / `RGB_UNDER_ZERO_ALPHA` — artifact heuristics only.

These flags must never be treated as automatic proof of a defect.
A final call still requires visual inspection.

## Latest-run pointer
Every successful run rewrites:
`E:\BASARA_WORK\ARC_TEXTURE_GALLERIES\LATEST.json`

Future chats should use this pointer instead of searching the output tree manually.

## Scope note
"Game-view" means the texture is decoded to the RGBA colour/alpha the game renders.
It does not attempt to reconstruct the complete LSP screen composition.
If a future task needs exact screen-layout reconstruction, add an LSP renderer as a separate layer rather than changing the texture decoder.
