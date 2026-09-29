---
name: basara-project-state
description: Mandatory first gate for BASARA Foundry current-state, ownership, donor, mutation, QA, release and handoff work. Establish machine health, search scope, quarantine, per-agent worktree and exact live bytes before historical evidence.
---

# BASARA project-state gate

Before substantive work, when the workspace exposes the local control plane:

1. run/read `.foundry/tools/status.py`;
2. read `.foundry/PROJECT_CURRENT.json`;
3. read `.foundry/SEARCH_SCOPE.json` and obey active/excluded surfaces;
4. read `.foundry/QUARANTINE.json`;
5. read `.foundry/AGENT_WORKTREES.json` and use only this agent's assigned writable worktree;
6. read/hash the exact current live target;
7. read only the relevant current domain skill/canon;
8. use current runtime-bound evidence/query output;
9. search historical Drive/archive/plugin references only if current sources are insufficient.

Do not begin from a broad recursive search of the workspace, Drive mirror, backups, old handoffs or embedded bulk maps.

## Health semantics

- `PASS`: proceed normally.
- `WARN`: inspect the warned component before relying on it; targeted exact-live work may still proceed.
- `FAIL`: do not make project-wide current-state/owner claims or mutate through the failed component until repaired.

## Snapshot freshness

If `PROJECT_CURRENT.json.snapshot.status == DIRTY`:
- snapshot-wide owner maps, manifests and censuses are navigation only;
- refresh state or validate the exact live target directly;
- label stale snapshot results as navigation.

A targeted task may proceed while the global snapshot is dirty when the exact target is freshly read and hash-bound.

## Current resource/provider query

Prefer the compact runtime-bound current query interface when available:

`.foundry/tools/query_current_compact.py <resource-fragment>`

Treat tied first runtime ranks as ambiguous; do not invent a winner from row/order position.

## Multi-agent isolation

Never share a writable Git working tree between GPT, Claude, Codex or another agent. Do not switch/reset/merge/stash/resolve/delete another agent's work. Integrate through a separate integration worktree.

## Authority

- current live bytes = production-state authority;
- current repository canon/tools/skills = durable engineering authority;
- current runtime-bound `.foundry` evidence = current provider evidence where applicable;
- Drive mirrors, archived workspaces, old handoffs and tombstoned plugin maps = supporting/history only;
- rejected candidates and quarantined rules/tools = never production authority.

A filename containing FINAL, FIXED, CANON, MASTER, CURRENT, READ_FIRST or ROOT_READY establishes nothing by itself.

## Transaction rule

`BACKUP -> HASH VERIFY -> MUTATE LIVE -> RE-READ -> RE-HASH -> REPARSE -> RUNTIME TEST`

Record source/final hashes, owner set, approval state, backup, touched files and runtime outcome.
