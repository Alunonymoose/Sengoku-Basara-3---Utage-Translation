# BASARA Foundry v0.2 Orchestration

This directory is the machine-truth layer for the Sengoku BASARA 3 Utage English project.

It does not replace the existing ARC/XET/GSM/FIM tools. It binds them to an exact live-tree snapshot so humans and agents stop relying on stale handoffs, filenames, or memory.

## Core rule

A factual claim about the current build must be bound to a snapshot_id (the SHA-256 of the complete live PS3_GAME file manifest). A patch recipe must also bind the exact provider ARC hashes and candidate-art hash. If those bytes change, the recipe is stale and validation fails.

## First usable workflow

From the repository root on the Windows machine with the live build:

    .\project\foundry.ps1 snapshot 'E:\Utage Patching New' --git-commit <current-git-sha>
    .\project\foundry.ps1 status 'E:\Utage Patching New'
    .\project\foundry.ps1 query 'E:\Utage Patching New' 'id\texture\jpn\tenka\tenka_023_ID_HQ' --type-hash 0x241F5DEB --exact

If an RPCS3 log exists, bind observed load order:

    .\project\foundry.ps1 bind-log 'E:\Utage Patching New' 'C:\path\to\RPCS3.log'
    .\project\foundry.ps1 hazards 'E:\Utage Patching New'

The query result then shows every exact typed/path provider and, where the log provides evidence, the observed earliest provider.

## Snapshot contents

A snapshot is written under <live root>\.foundry\snapshots\<tree-sha256> and contains snapshot.json, files.json, index.sqlite3, parse_errors.json and arc_warnings.json.

When the supplied root contains PS3_GAME, only that live game tree is hashed. Backup/work folders beside PS3_GAME do not contaminate the runtime identity.

The SQLite index stores every file hash, every parsed ARC member, exact canonical resource identity (type hash plus ASCII-lowercased internal path), stored/expanded hashes, duplicate-provider divergence, and optional RPCS3-observed provider order.

ARC parsing is delegated to the pinned production safe_arc.py. RPCS3 log ranking is delegated to the existing basara_resource_ownership.py. The orchestration layer does not invent a competing parser.

## Patch recipes

Create a recipe only from an exact resource identity:

    .\project\foundry.ps1 recipe-new 'E:\Utage Patching New' 'id\texture\jpn\tenka\tenka_023_ID_HQ' --type-hash 0x241F5DEB --recipe-id lottery-tenka-023 --candidate .\art\tenka_023.png --encoder xet-0x2A-ycbcr-bc3 --out .\recipes\lottery-tenka-023.json

The recipe records every current provider ARC hash and resource hash. Approval is valid only for one exact candidate SHA-256. recipe-validate fails if the candidate or bound snapshot changes.

    .\project\foundry.ps1 recipe-validate .\recipes\lottery-tenka-023.json --snapshot 'E:\Utage Patching New' --require-candidate

## Safety boundary

This CLI is read-only with respect to game files. It does not install, rebuild, or mutate ARCs. Existing verified writers remain responsible for that step. v0.2 makes those writers consume explicit, hash-bound state instead of free-form instructions.

## Next integration milestones

1. Make the release auditor consume index.sqlite3 instead of rescanning independently.
2. Make Donor Matcher accept snapshot ID/resource identity directly.
3. Make the BASARA Foundry GUI show provider/approval state from this database.
4. Add recipe execution through the existing safe transaction harness.
5. Add golden screenshot records bound to snapshot ID and runtime-matrix row.
6. Add optional content-addressed private storage for large historical artifacts; Git remains source/spec/manifest authority.
7. Add formal binary specifications as independent verification fixtures without replacing production writers until parity tests pass.

## Hazard triage

`hazards` is the raw divergent-provider inventory. It is intentionally exhaustive and therefore noisy.

Use `triage` for engineering work:

    .\project\foundry.ps1 triage 'E:\Utage Patching New' --actionable --limit 50

The triage layer separates:

- `SAME_FAMILY_DIVERGENCE` — strongest structural hazard; different payloads inside the same route/load family.
- `SAME_ROUTE_CROSS_FAMILY_DIVERGENCE` — different payloads in ENG (or JPN) across different load families; often intentional but worth ownership analysis.
- `EXPECTED_ENG_JPN_DIVERGENCE` — one internally-consistent ENG payload versus one internally-consistent JPN payload; usually expected localisation and suppressed by `--actionable`.
- `CROSS_ROUTE_OR_CONTEXT_DIVERGENCE` — mixed cases needing context.
- `BACKUP_OR_DERIVATIVE` providers — likely live-tree contamination such as `- Copy.arc`, `*_backup.arc`, or same-directory derivative siblings.

A backup/derivative flag is a hygiene warning, not proof that RPCS3 loads that ARC. Never delete/move it solely from the flag; runtime/load evidence or reference checks must confirm it is not required.

## Special ARC containers

The production `safe_arc.parse_arc()` remains fail-closed on non-zero inter-payload gaps and trailers.

The snapshot index uses `safe_arc.inspect_arc()`, which keeps header/range/codec/overlap validation strict but records non-zero gap/trailer bytes as container anomalies. This allows special stock/live containers to be searchable without weakening mutation safety. Production rebuilds of those ARCs remain blocked until their extra bytes are understood and explicitly supported.
