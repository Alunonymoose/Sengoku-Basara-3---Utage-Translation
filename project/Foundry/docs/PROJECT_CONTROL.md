# Project Control and State Authority

This document defines how an AI or human should decide what is current.

## Authority order

1. Current live production bytes supplied by the maintainer.
2. A fresh read/hash of the exact target resource.
3. Workspace machine state such as `.foundry/PROJECT_CURRENT.json`.
4. Current domain canon/skill from this repository.
5. Runtime evidence bound to the exact installed output.
6. Historical Drive notes, backups, handoffs and archived workspaces.

A filename containing `FINAL`, `CANON`, `MASTER`, `CURRENT` or `READ FIRST` is not authority by itself.

## Snapshot freshness gate

A content-addressed snapshot is useful only while it still represents the live tree.

When a workspace provides `.foundry/PROJECT_CURRENT.json`:
- if `snapshot.status == CLEAN`, snapshot-wide ownership/census claims may be used subject to normal evidence rules;
- if `snapshot.status == DIRTY`, do not make whole-tree/current-owner claims from that snapshot without refreshing it or re-reading the exact live target.

A targeted job may still proceed against a freshly hashed live ARC while the global snapshot is dirty.

## Workspace separation

Recommended physical separation:

- live retail tree: production bytes only;
- source repository: canon, tools, schemas, tests and skills;
- work/jobs: transient candidates, decodes and audits;
- backups: immutable transaction backups;
- archive/quarantine: rejected candidates, superseded handoffs and legacy tools.

Do not make broad searches over all five surfaces the default recovery method.

## Retrieval order for agents

`PROJECT_CURRENT -> exact live target -> domain skill/canon -> runtime evidence -> historical research`

Broad historical search is escalation, not bootstrap.

## Transaction rule

Production mutation should follow:

`BACKUP -> HASH VERIFY -> MUTATE -> RE-READ -> RE-HASH -> REPARSE -> RUNTIME TEST`

Every transaction should record target hashes, owner set, approval state, backup location, touched files and runtime outcome.

## Visual-family rule

For a new visual family, prove a representative candidate in the real runtime slot before batch fanout. Style authority and layout/slot authority may be different resources.

## Quarantine rule

Disproven tools, rejected candidates and superseded rules must remain searchable for provenance but must be excluded from default donor/production authority.
