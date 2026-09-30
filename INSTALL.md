# Installing the English patch

This page is for players who already have their own extracted/dumped copy of **Sengoku BASARA 3 Utage** for PlayStation 3.

## Supported game

- **Title:** Sengoku BASARA 3 Utage
- **Platform:** PlayStation 3
- **Title ID:** **BLJM60389**

The project does not provide the game, an ISO/disc image, or complete replacement retail game files.

## What the public patch will do

The v0.1 release package is intended to patch an existing extracted game directory in place.

The patcher works from a manifest that records:

- each file that needs changing;
- the SHA-256 hash of the supported original file;
- the SHA-256 hash expected after patching;
- the delta patch to apply.

This lets the installer refuse unknown game revisions instead of blindly overwriting files.

The current localisation architecture uses the game's normal PS3 file tree, including the project's English `nativePS3/rom/eng` route and the required executable/resource changes.

## Expected game layout

Point the installer at the folder containing `PS3_GAME`.

Example:

```text
Sengoku BASARA 3 Utage/
└── PS3_GAME/
    ├── PARAM.SFO
    ├── USRDIR/
    │   └── nativePS3/
    │       └── rom/
    └── ...
```

Do **not** point it at the repository itself.

## v0.1 installation

When a v0.1 release package is published:

1. Make a backup of your unmodified game folder.
2. Download the latest v0.1 patch release from this repository's **Releases** page.
3. Extract the patch package somewhere outside the game directory.
4. Run `apply_patch.ps1` from PowerShell, passing the game folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\apply_patch.ps1 -GameRoot "D:\Games\Sengoku BASARA 3 Utage"
```

5. The installer will:
   - locate `PS3_GAME`;
   - verify required original file hashes;
   - stop if the game revision does not match;
   - create backups of files it will modify;
   - apply binary delta patches;
   - verify every resulting SHA-256 hash.

6. Launch the patched game normally on your supported PS3/RPCS3 setup.

## If verification fails

Do not force the patch.

A failed original-file hash normally means one of the following:

- the game is not BLJM60389;
- the files have already been modified;
- the dump is incomplete/damaged;
- a different update/revision is installed.

Restore a clean copy and try again.

## Current repository status

The repository currently contains the public research, tooling and engineering canon. The end-user installer framework is being prepared for the first public **v0.1 preview/test release**.

The actual v0.1 delta payloads must be generated from the current approved live localisation build before the release can be considered installable.

## PS3 and RPCS3

The translation project is designed around modifications that can exist in the real PS3 game filesystem rather than emulator-only runtime patches. RPCS3 remains useful for testing, but the public patch format should remain usable with a legitimate extracted PS3 game tree.

## Reporting a problem

When reporting an installation problem, include:

- the exact installer error;
- the file path named by the installer;
- the SHA-256 it found;
- whether your game was clean before patching.

Do not upload or attach retail game files to an issue.
