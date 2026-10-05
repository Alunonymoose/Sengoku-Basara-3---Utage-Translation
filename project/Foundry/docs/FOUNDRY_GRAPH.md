# Foundry Graph â€” executable project state

Status: implemented 2026-09-30.

## Purpose

Foundry Graph is the rebuildable machine-readable index for the Utage project. It does **not** replace live game bytes, current JSON certificates, Git history or runtime evidence. It derives fast answers from them.

Default database:

`E:\Utage Patching New\.foundry\cache\foundry_graph.sqlite`

The database is disposable. Delete it and run `foundry build` to recreate it.

## Indexed authority layers

- `ENG` â€” current live `rom\eng` production tree.
- `JPN` â€” current live `rom\jpn` reference tree.
- `SH` â€” Samurai Heroes official-English reference tree when locally available.
- current RPCS3 log opens under `nativePS3`.
- machine-readable folder/file sign-off certificates.

Every indexed file records role, logical path, size, mtime and SHA-256. Every parsed ARC member records stable member index, internal path, type hash, compression metadata, raw/stored SHA-256, detected resource kind and XET metadata when applicable.

## Current commands

From repository `project`:

```powershell
.\foundry.ps1 build
.\foundry.ps1 status
.\foundry.ps1 query "mode_select_000"
.\foundry.ps1 owners "common_025"
.\foundry.ps1 why "title_004"
.\foundry.ps1 audit
.\foundry.ps1 show "title.arc"
.\foundry.ps1 certify "PS3_GAME/USRDIR/nativePS3/rom/eng/demo" --name ROM_ENG_DEMO
.\foundry.ps1 signoffs
```

`show` uses the project-certified XET display decoder and creates the numbered PDF texture-book workflow.

## Sign-off invalidation

A sign-off certificate contains the complete file list, size and SHA-256 for its scope at certification time.

`foundry status` and `foundry signoffs` re-hash those live files.

- `VALID` â€” every certified file still exists and hashes identically.
- `STALE` â€” at least one certified file is missing or changed.
- `ERROR` â€” certificate itself cannot be evaluated.

This makes "100% complete" a byte-bound state rather than a historical note.

Certificates live under:

`E:\Utage Patching New\.foundry\signoffs\*.signoff.json`

## Texture triage

`foundry audit` builds a whole-tree priority queue without mutating anything.

Signals currently include:
- byte-identical to Utage JPN with no exact official SH donor;
- custom/Utage English texture with no exact official SH donor;
- exact official SH payload;
- current RPCS3 log participation;
- valid signed-off folder exclusion.

Outputs:

`E:\Utage Patching New\.foundry\TEXTURE_TRIAGE.json`
`E:\Utage Patching New\.foundry\TEXTURE_TRIAGE.csv`

Heuristics are **triage only**. A score never authorizes a patch.

## Comparison policy

JPN comparison is route-bound.

Samurai Heroes comparison first tries equivalent route/member identity, then searches the indexed SH corpus by resource basename + type, preferring an exact raw-payload match. This deliberately allows official donors to be recognized when SH archive topology differs from Utage.

## Runtime evidence

The graph ingests the current RPCS3 log as path/open-count evidence. Runtime presence strengthens prioritization and ownership investigation but does not by itself prove final provider precedence.

## Known structural warnings

The certified `safe_arc.py` parser intentionally fails closed on unexplained non-zero ARC trailers. Reference-tree parse warnings therefore remain visible rather than being silently relaxed.

As of 2026-09-30 two JPN reference archives trigger this guard:
- `common/pl_face/pl_all.arc`
- `tenka/friend.arc`

These are research warnings, not a reason to weaken production parsing.

## Reproducibility rule

The graph fingerprint is SHA-256 over sorted `(role, logical path, file SHA-256)` tuples. Rebuilding against unchanged inputs must reproduce the same fingerprint.

A new durable project fact should become one of:
- a parser/test;
- a machine-readable certificate;
- an indexed relation/query;
- a public-safe canon update.

It should not remain only in chat memory.