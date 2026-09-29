# Project Control and State Authority

This document defines how an AI or human should decide what is current.

## Bootstrap / authority order

When a workspace provides the current control plane, start with:

1. `.foundry/tools/status.py`;
2. `.foundry/PROJECT_CURRENT.json`;
3. `.foundry/SEARCH_SCOPE.json`;
4. `.foundry/QUARANTINE.json`;
5. `.foundry/AGENT_WORKTREES.json`;
6. a fresh read/hash of the exact current live target;
7. current domain canon/skill from this repository;
8. runtime evidence/query output bound to the target;
9. historical Drive notes, backups, handoffs, plugin tombstones and archived workspaces only when needed.

A filename containing FINAL, FIXED, CANON, MASTER, CURRENT, READ FIRST or ROOT_READY is not authority by itself.

## Snapshot freshness gate

When `PROJECT_CURRENT.json.snapshot.status == CLEAN`, snapshot-wide ownership/census claims may be used subject to normal evidence rules.

When it is `DIRTY`:
- whole-tree/current-owner claims from that snapshot are blocked;
- refresh the snapshot or read/hash the exact live target directly;
- stale snapshot results are navigation only.

A targeted job may still proceed against freshly verified live bytes while the global snapshot is dirty.

## Current provider/resource query

Prefer the current compact query interface when available:

`.foundry/tools/query_current_compact.py <resource-fragment>`

It is intentionally compact, groups duplicate payloads and must report tied earliest runtime providers as ambiguous rather than picking one by row order.

## Workspace separation

- live retail tree: production bytes only;
- source repository/worktrees: canon, tools, schemas, tests and skills;
- work/jobs: transient candidates, decodes and audits;
- backups: immutable transaction backups;
- archive/quarantine: rejected candidates, superseded handoffs and legacy tools.

Broad searches across all surfaces are escalation, not bootstrap.

## Multi-agent isolation

Never share one writable Git working tree between GPT, Claude, Codex or another agent. Obey `.foundry/AGENT_WORKTREES.json` and integrate separately.

## Transaction rule

`BACKUP -> HASH VERIFY -> MUTATE LIVE -> RE-READ -> RE-HASH -> REPARSE -> RUNTIME TEST`

Every transaction should record target hashes, owner set, approval state, backup location, touched files and runtime outcome.

## Visual-family rule

For a new visual family, prove representative candidate(s) in the real runtime slot before batch fanout. Style authority and layout/slot authority may be different resources.

## Quarantine rule

Disproven tools, rejected candidates and superseded rules remain searchable for provenance but are excluded from default donor/production authority.
