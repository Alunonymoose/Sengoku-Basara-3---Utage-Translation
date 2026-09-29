---
name: basara-project-state
description: Mandatory bootstrap and authority gate for BASARA Foundry current-state, ownership, donor, mutation, QA, release and handoff work. Read machine state, per-agent worktree registry and exact live bytes before historical maps or snapshots.
---

# BASARA project-state gate

Before substantive work:

1. If the workspace provides `.foundry/PROJECT_CURRENT.json`, read it first.
2. If it provides `.foundry/AGENT_WORKTREES.json`, use only the worktree assigned to this agent.
3. Read/hash the exact current live target before mutation.
4. Read only the relevant current domain skill/canon.
5. Use runtime evidence bound to the exact target.
6. Search historical notes/backups only if current sources are insufficient.

Do not begin from a broad recursive search of the whole workspace.

## Snapshot freshness

If `PROJECT_CURRENT.json.snapshot.status == DIRTY`:
- do not claim a whole-tree owner map, census or manifest is current;
- refresh the snapshot or validate the exact live target directly;
- label stale snapshot results as navigation only.

A targeted task may proceed while the global snapshot is dirty if the exact target is freshly read and hash-bound.

## Multi-agent isolation

Never share a writable Git working tree between GPT, Claude, Codex or another agent.

When `AGENT_WORKTREES.json` exists:
- obey the registered per-agent worktree;
- do not switch branches in another agent's worktree;
- do not reset, merge, checkout, stash, resolve or delete another agent's in-progress/unmerged work;
- integrate through a separate integration branch/worktree.

Live game bytes remain outside agent Git worktrees.

## Authority

Current live bytes win for production state.
Repository canon/tools/skills are durable engineering authority.
Drive mirrors, old handoffs, backup directories and generated reports are supporting evidence only unless explicitly promoted.
Rejected candidates, superseded handoffs and quarantined tools are excluded from default production authority.

## Transaction rule

For live mutation:
`backup -> hash verify -> mutate -> read back -> re-hash -> reparse -> runtime test`

Record the transaction in a job manifest.

## Retrieval hygiene

Default retrieval order:

`PROJECT_CURRENT -> AGENT_WORKTREES -> exact live target -> domain skill/canon -> exact runtime evidence -> historical research`
