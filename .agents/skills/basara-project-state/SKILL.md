---
name: basara-project-state
description: Mandatory bootstrap and authority gate for BASARA Foundry work. Use before current-state, ownership, donor, live-mutation, release, QA, or cross-agent handoff work.
---

# BASARA project-state gate

Before substantive work, establish the current project state.

## Bootstrap order

1. If the workspace provides `.foundry/PROJECT_CURRENT.json`, read it first.
2. Read/hash the exact live target resource before mutation.
3. Read only the relevant current domain skill/canon.
4. Use runtime evidence bound to the target when available.
5. Search historical notes/backups only when the current sources do not answer the question.

Do not begin from a broad recursive search of the whole workspace.

## Snapshot rule

If `PROJECT_CURRENT.json.snapshot.status` is `DIRTY`:
- do not claim a whole-tree owner map, census or manifest is current;
- either refresh the snapshot or validate the exact live target directly;
- label stale snapshot results as navigation only.

## Authority rule

Current live bytes win for production state.
Repository canon/tools/skills are durable engineering authority.
Drive mirrors, old handoffs, backup directories and generated reports are supporting evidence only unless explicitly promoted.

## Transaction rule

For live mutation:
`backup -> hash verify -> mutate -> read back -> re-hash -> reparse -> runtime test`

Record the transaction in a job manifest.

## Retrieval hygiene

Ignore by default:
- rejected candidate folders;
- superseded handoffs;
- ROOT_READY packages from older workflow phases;
- quarantined writers;
- historical workspaces copied under the live root.

Escalate to them only for provenance or when current sources are insufficient.
