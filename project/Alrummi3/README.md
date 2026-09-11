# Alrummi 3

Alrummi 3 is an offline-first, AI-assisted ARC texture localization workbench for Sengoku Basara 3 Utage.

The ARC browser follows the public Kuriimu2 MT Framework plugin structure and
now supports recursively opening every readable `.arc` under a selected folder.
See `KURIIMU2_INTEGRATION.md` for the upstream source references.

It is designed as an upgraded, focused Kuriimu-style workflow:

1. Open an MT Framework ARC v8 archive.
2. Open a folder to batch-load all nested ARC archives, then switch between them from the archive selector.
3. Search the archive and select a texture/resource.
4. Preview the Japanese source with zoom, pan, and checkerboard transparency.
   Shift+drag on the source picks the text region directly; plain drag still pans.
5. Open GSM/`.msg` resources in the readable MSG viewer, with record boundaries and control-code tags.
6. Ask a local Ollama vision model to suggest the English translation and text region, or enter both manually.
7. Generate a polished, same-dimensions visual copy locally. Long wording is wrapped into a readable heading instead of being compressed into a single tiny line.
8. Find the matching `/jpn` archive/resource automatically and open it in a reference preview tab.
9. Open the **SH donors** tab to reuse the official English texture from Samurai Heroes.
   Build the index once, search for the selected resource, choose a resize mode, and load
   the donor as the candidate. An exact-size donor is copied block for block with no
   quality loss.
9. Review the complete side-by-side preview, or open a loose image and save its candidate as PNG.
10. Use the integrated local chat to refine translations and layout instructions beyond the fixed buttons.
11. Tick the confirmation box and save a new ARC plus an audit report.
12. Shift+drag the source to add **repair boxes**, then patch just that
    rectangle from the donor, letter it, or erase it — for fixing part of a
    texture without touching the rest.
13. Use the **Dialogue editor** to translate `msg_m###_pl###.arc` speech by
    speech, auto-filled from the project's 14,948-entry dictionary, with live
    41-column / 3-line validation and per-speech sign-off.
14. Use **Dialogue batch** to survey and build every dialogue archive at once.
    A survey of all 1,410 takes about 47 seconds; building the 1,097 that are
    ready takes about 6.5 minutes. Only archives passing all five of the
    project's build invariants are written.
15. **Install into game tree** replaces an archive after backing the original
    up, and **Installs / revert** puts any of them back.

The source ARC is never overwritten. The write step preserves untouched compressed blobs, entry order, type hashes, flags, and resource names, and verifies that exactly one entry changed.

## Drive-backed ChatGPT factory

For high-quality art that benefits from ChatGPT's image editing but should not use the paid image API, Alrummi now has a Drive-backed handoff layer:

- `drive_factory.py` creates a self-contained job in a locally synced Google Drive folder.
- Each job can contain the full source atlas, pristine JPN reference, Samurai Heroes donor, current ENG state, in-game mockup, contact sheet, sprite crops, edit regions, manifest, and prompt.
- ChatGPT returns one full-size `replacement.png` to the matching OUTBOX job folder.
- `drive_factory_controller.py` can poll OUTBOX without blocking Tk, validate the returned image, and deliver it to the GUI as a candidate.
- Remote results never write an ARC directly. User approval remains mandatory before the existing rebuild/install path.
- If editable regions are known, the validator can reject unrelated changes outside those boxes instead of accepting a generator-redrawn atlas.

See `DRIVE_FACTORY.md` for the queue structure and the narrow v31 integration contract. Run `python drive_factory_selftest.py` for the offline safety checks.

## Run

From PowerShell:

```powershell
cd 'E:\Utage Patching New\Alrummi3'
python -m pip install -r requirements.txt
python alrummi3_gui.py
```

For a double-click launcher, run `Open_Alrummi3.ps1` from this folder.

To build the standalone Windows executable, install PyInstaller once and run
`Build_Alrummi3.ps1`. The result is `dist\Alrummi3.exe`; the build also places
`ai_extensions` and `updates` beside it so future AI updates remain portable.
The first launch creates a small `Alrummi3_runtime` folder beside the EXE for
the bundled offline Tk runtime; this avoids the broken system Tcl path found
on some Windows Python installations.

The app has no cloud dependency. For local AI assistance, run Ollama locally and have the models available on the machine:

```text
http://127.0.0.1:11434
vision model: qwen2.5vl:7b
text model: qwen2.5:3b
```

If Ollama is not running, Alrummi 3 still works as a manual translation and candidate-rendering tool.

## Current scope

- ARC v8 archives with big-endian `\0CRA` and little-endian `ARC\0` headers.
- XET textures with BC3/DXT5 preview and confirmed replacement support.
- XET DXT1 preview is supported, but write confirmation is blocked because a safe DXT1 encoder is not yet included.
- Common PNG/JPEG/BMP/TGA image resources when they occur directly in an archive.

The first release deliberately does not claim that an offline archive audit proves in-engine fit. After installing a confirmed ARC in the game tree, cold-boot RPCS3 and check the affected screen.

## Suggested next upgrades

- Add a drag-to-select text-region overlay on the preview.
- Add donor-texture matching against the existing Samurai Heroes English reference tree.
- Add XET swizzle variants and native BC1/DXT1 encoding after fixture-based validation.
- Add LSP/PSL layout inspection beside each texture so text overflow can be corrected in the same review.
- Add project sessions with undoable candidate history and cumulative package export.
