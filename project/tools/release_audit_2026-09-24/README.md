# BASARA Foundry Release Audit — 2026-09-24

This folder is the implementation home for the read-only whole-live release audit described by the Foundry document:

**00 RELEASE AUDIT ORCHESTRATOR — IMPLEMENTATION CONTRACT — 2026-09-24**

## Current status

`foundry_release_audit.py` is a deliberately fail-closed bootstrap, not a finished release certifier.

Implemented now:

- hashes every file under the supplied live root;
- classifies basic file families;
- imports the pinned canonical `safe_arc.py` and refuses silent hash drift;
- parses every ARC through `safe_arc.py`;
- emits a complete ARC-member inventory;
- invokes the existing Resource Ownership Analyzer rather than reimplementing ownership logic;
- inventories every rTexture through the recovered solved-XET reader;
- decodes/hash-fingerprints supported level-0 texture RGBA;
- intercepts 0x15 before image decode and emits it as quarantined;
- extracts divergent/unresolved provider classes;
- emits one `UNRESOLVED.json` queue;
- records tool hashes and run metadata;
- emits output hashes.

Not yet integrated:

- semantic visual classification/contact-sheet review on top of the structural texture census;
- 0x15 BC2-vs-BC3 fixture revalidation;
- recovered GSM/FIM message census;
- PAM/media census;
- PARAM.SFO/XMB/TROPDIR/loose semantic census;
- Donor Matcher V5.1 sweep;
- runtime-acceptance merge.

Because those release-critical stages are missing, a successful bootstrap audit returns **exit code 1**, never 0.

## Usage

Example:

    python project/tools/release_audit_2026-09-24/foundry_release_audit.py "E:\\Utage Patching New" --sh-root "E:\\SAMURAI HEROES" --rpcs3-log "C:\\path\\to\\RPCS3.log" --out "E:\\BASARA_AUDITS\\2026-09-24"

The output directory must be outside the live game root.


## Windows live-E launcher

Use:

`project/tools/release_audit_2026-09-24/run_release_audit.ps1`

Default roots:

- `E:\\Utage Patching New`
- `E:\\SAMURAI HEROES`
- audit output root `E:\\BASARA_AUDITS`

The launcher now also:

- records the exact Git repo HEAD in `LAUNCH_CONTEXT.json` when available;
- finds the newest previous audit under the audit root;
- runs `compare_audits.py` automatically against that prior snapshot;
- emits a full audit-artifact SHA-256 map;
- keeps the audit directory outside the game tree;
- returns the auditor's fail-closed status rather than converting engineering blockers into success.

Use `-NoPreviousDiff` only when an isolated baseline run is desired.

This makes the normal production loop:

`current E: -> audit -> patch -> audit -> automatic delta -> runtime evidence`.

## Exit codes

- `0` — reserved for a future complete release audit with no release blockers/unknowns.
- `1` — audit completed but release blockers, unknowns, review items, or unimplemented stages remain.
- `2` — dependency/tool failure.
- `3` — invalid/incomplete input root or unsafe output location.

The current bootstrap intentionally returns `1`.

## Canonical dependencies

### ARC

`../donor_matcher_v5_1_2026-09-23/safe_arc.py`

Pinned SHA-256:

`f25c53e4ad78e18d5785b8aee197725377130ed9f562a9caa1000a1964bde91d`

The orchestrator refuses a changed `safe_arc.py` unless `--allow-tool-drift` is supplied. That override is engineering-only and can never make a run release-passing.

### Ownership

`../resource_ownership_2026-09-23/basara_resource_ownership.py`

The orchestrator executes the existing analyzer. It does not infer runtime precedence from filesystem ordering.

## 0x15 quarantine

Current Foundry canon contains a resolved process rule but an unresolved format-classification conflict:

- real 2026-09-22 Utage fixture evidence supports 0x15 as DXT3/BC2;
- later 2026-09-23 summary prose grouped 0x15 with BC3/DXT5.

Until the exact fixture is revalidated with the current decoder, every audit carries an explicit `XET_0X15_FORMAT_QUARANTINE` blocker. Production writing is disabled.

## Output contract — bootstrap

Implemented:

- `00_RUN_METADATA.json`
- `FILE_TREE_HASHES.json`
- `FILE_TREE_HASHES.csv`
- `ARC_MEMBERS.json`
- `ARC_MEMBERS.csv`
- `RESOURCE_OWNERSHIP.json`
- `DIVERGENT_PROVIDERS.json`
- `TEXTURE_CENSUS.json`
- `TEXTURE_CENSUS.csv`
- `UNRESOLVED.json`
- `AUDIT_SUMMARY.md`
- `SHA256SUMS.json`

Explicit fail-closed placeholders are also emitted for not-yet-wired stages so downstream automation cannot mistake their absence for success.

## Development order

1. add tests for bootstrap hashing, safe-ARC pinning, output-location refusal and ARC parse failure;
2. generate visual review/contact sheets and semantic texture dispositions;
3. revalidate/quarantine 0x15 correctly;
4. wire recovered GSM/FIM grammar;
5. wire media and loose/platform censuses;
6. wire Donor Matcher V5.1 discovery-only output;
7. add stable diff mode;
8. merge runtime acceptance evidence;
9. run against exact current live E: and promote only after no silent omissions are demonstrated.

## Safety rules

- read-only;
- no auto-patching;
- no auto-donor install;
- no language classification based only on `eng/jpn` path or hash equality;
- no filesystem-order runtime precedence;
- no hidden parser failures;
- unknown is emitted as unknown;
- missing stage is a blocker, not a pass.
