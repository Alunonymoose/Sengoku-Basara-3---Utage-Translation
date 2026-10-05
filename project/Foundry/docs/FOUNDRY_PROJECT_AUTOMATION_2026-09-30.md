# Foundry Project Automation — 2026-09-30

Status: implemented on `foundry-v0.4-graph`.

This layer turns the Foundry Graph from a passive index into a day-to-day project control system.

## Commands

From the repository `project` directory:

```powershell
.\foundry.ps1 doctor
.\foundry.ps1 next
.\foundry.ps1 impact "title.arc"
.\foundry.ps1 compare-trees <build-A> <build-B>
```

Existing commands remain:

```powershell
.\foundry.ps1 build
.\foundry.ps1 status
.\foundry.ps1 query "resource"
.\foundry.ps1 owners "resource"
.\foundry.ps1 why "resource"
.\foundry.ps1 audit
.\foundry.ps1 ocr-audit
.\foundry.ps1 show "title.arc"
.\foundry.ps1 signoffs
.\foundry.ps1 runtime-bind
.\foundry.ps1 runtime-status
```

## `foundry doctor`

Writes:

`E:\Utage Patching New\.foundry\PROJECT_HEALTH.json`

The doctor checks the project as one system rather than trusting any single note.

Current checks:

- `.foundry/PROJECT_CURRENT.json` readability;
- Foundry Graph database/status fingerprint agreement;
- live ENG ARC parse health;
- every machine-readable sign-off against current live hashes;
- hashes of the canonical XET/ARC/parser tools recorded in `PROJECT_CURRENT.json`;
- current snapshot freshness state;
- canonical Git worktree branch + dirtiness;
- exact-commit validation for `third_party/ORACLES.lock.json`;
- runtime acceptance matrix binding against the current graph fingerprint;
- active-root hygiene report.

Severity:

- **FAIL** — production authority or integrity is contradicted;
- **WARN** — safe to continue only with the warning understood, e.g. a dirty historical snapshot;
- **PASS** — current machine-readable evidence agrees.

`foundry doctor --strict` also returns non-zero for warnings.

The doctor does not make historical snapshots authoritative. Exact current live bytes remain production authority.

## `foundry next`

Ranks unsigned top-level ENG folders using current graph facts rather than chat recollection.

Signals include:

- number of textures still byte-identical to Utage JPN without an exact official Samurai Heroes donor;
- number of custom/Utage textures without an exact official donor;
- untranslated-looking message-family resources as a weaker signal;
- current RPCS3 log participation;
- estimated effort from ARC count and live byte size;
- exclusion of currently VALID signed-off scopes.

The score is prioritization only. It is not evidence that a resource is wrong.

This command is intended to answer questions like:

- “what folder should we finish next?”
- “what is the highest-value cleanup target?”
- “what should another agent work on?”

without rebuilding that judgement manually every session.

## `foundry impact`

Run this before mutating a live ARC when there is any chance it participates in a shared family.

Example:

```powershell
.\foundry.ps1 impact "title.arc"
```

The report shows:

- whether changing the file will invalidate an existing sign-off;
- current indexed file identity;
- resource count;
- payload-identical resources owned by other archives/routes;
- same-name resources in other archives/routes.

It does not claim that every duplicate is a runtime owner. It is a pre-mutation hazard report that tells the engineer where owner synchronization must be investigated.

## `foundry compare-trees`

Byte-compares two output/build trees and exits non-zero if they differ.

It reports:

- identical file count;
- changed files with size/SHA-256 on each side;
- files only present on the left;
- files only present on the right;
- overall `reproducible` boolean.

The intended production rule is:

> same live input hashes + same approved manifest + same pinned tools must produce byte-identical outputs.

This tool is the first generic enforcement layer for that rule. Individual builders should progressively gain dedicated rebuild-twice regression tests.

## CI

`.github/workflows/foundry-core.yml` now:

1. compiles every public-safe Python Foundry control tool;
2. runs every `project/Foundry/tests/test_*.py` regression through unittest discovery.

New project-control tools therefore cannot silently become syntax-invalid or break their synthetic regressions without failing CI.

## Authority model

These tools deliberately preserve the project's existing precedence:

1. user's explicit current request;
2. exact current live game bytes;
3. current machine-readable Foundry state and runtime evidence;
4. current repository code/tests/canon;
5. historical notes/backups;
6. generic external engine knowledge.

Automation should reduce rediscovery, not hide uncertainty.
