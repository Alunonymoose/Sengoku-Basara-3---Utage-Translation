---
name: basara-project-state
description: Mandatory portable bootstrap and authority gate for BASARA Foundry current-state, ownership, donor, mutation, QA, release and handoff work.
---

# BASARA Foundry Project-State Gate

## Bootstrap

1. If the workspace provides `.foundry/PROJECT_CURRENT.json`, read it first.
2. Read/hash the exact current live target.
3. Read only the relevant current domain canon/skill.
4. Use runtime evidence bound to the target.
5. Search historical notes/backups only if current sources are insufficient.

## Snapshot freshness

If `PROJECT_CURRENT.json.snapshot.status == DIRTY`, snapshot-wide owner maps, manifests and censuses are navigation only. Refresh the snapshot or validate the exact live target directly.

## Authority

- fresh live bytes = production state authority;
- current repository canon/tools/skills = durable engineering authority;
- Drive mirrors, old handoffs and backups = supporting evidence only;
- rejected candidates and quarantined tools = never production authority.

A filename containing FINAL/FIXED/CANON/MASTER/CURRENT/READ_FIRST is not authority by itself.

## Retrieval order

`PROJECT_CURRENT -> exact live target -> current skill/canon -> exact runtime evidence -> historical research`

## Mutation transaction

`BACKUP -> HASH VERIFY -> MUTATE -> RE-READ -> RE-HASH -> REPARSE -> RUNTIME TEST`
