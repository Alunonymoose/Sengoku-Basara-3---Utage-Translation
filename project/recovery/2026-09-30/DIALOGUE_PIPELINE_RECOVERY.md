# Dialogue / GSM / FIM Pipeline Recovery — 2026-09-30

## Preserved production implementation

The solved production dialogue repair toolchain is already present in this branch:

`project/dialogue_tools/fim_contract_recovery_2026-09-20/`

Preserved files:
- `README.md`
- `FIM_CONTRACT_REPAIR.py`
- `FIM_CONTRACT_ROLLBACK.py`
- `GLUED_RUN_REPAIR.py`
- `SEPARATOR_REPAIR.py`
- `SCAN_TEXT_DEFECTS.py`

Additional preserved support:
- `project/pipeline/dialogue_integrity_guard.py`
- `project/FIX_dialogue_desync.ps1`
- `project/UNDO_dialogue_desync.ps1`
- `project/forensics/COLLECT_dialogue_runaway_forensics.ps1`
- `project/forensics/DEEPSEEK_ASSIGNMENT_DIALOGUE_RUNAWAY_ROUTE_DIVERGENCE.md`
- `project/Alrummi3/msg_batch.py`
- `project/Alrummi3/msg_edit.py` (legacy/provenance; not authoritative production grammar)

## Recovered GSM/FIM contract

- GSM descriptor offsets/lengths are 16-bit code units.
- Control grammar includes:
  - FC0E argc=2
  - FC0F argc=1
  - FC12 argc=0
  - FC16 argc=1
  - FC17 argc=3
  - FED2 argc=2
  - FF91 argc=0
  - FF92 argc=1
  - FFFA argc=1
  - FFFB argc=1
  - FFFD argc=0 — speech delimiter
  - FFFE argc=0 — visual line increment
  - FFFF argc=0
- FIM secondary col0 = `(visual_line_count << 16) | visible_glyph_count`.
- FIM secondary col1 high16 = speech start offset in GSM units.
- Rebuilt ARC must be reparsed and untouched members/metadata verified.

## Recovered source hashes from the canonical recovery record

- FIM_CONTRACT_REPAIR.py
  `2dda5bcbba10d20467fe91ae9a1e3e0bc0422ab4fcb8e4e7cb2a232dca985013`
- FIM_CONTRACT_ROLLBACK.py
  `5eff33ffdead394fdba6b5269d95d67c2cf7cfc207c63ccf504b718b9ee5771b`
- GLUED_RUN_REPAIR.py
  `63f59e78abd4dc996f58b980aa37ce201baf2ec4eb5b26582cd1a98292ab1e50`
- SEPARATOR_REPAIR.py
  `a19ba0d7397c743ff483032e8d9e2d3dafdf457d7468bbb38d61ecf454ce4548`
- SCAN_TEXT_DEFECTS.py
  `bba221464414ceeb40ab5ecd82f417140555832214efb031be7552bec7587c66`

## Legacy warning

The loose/older `msg_edit.py` lineage predates the final grammar and historically had incorrect FC17/FF91 assumptions. Do not promote it above the recovered FIM contract without updating it and testing fixtures.

## Drive canon provenance

Google Drive document:
`00 READ FIRST — RECOVERED MSG-FIM PRODUCTION TOOLCHAIN — 2026-09-20`

Drive document id:
`1DgCi0gULOflKlkUK2wtOOe2twKMWlEeVVFf85BG9I4Y`

The actual recovered scripts are on GitHub, so dialogue production knowledge is materially backed up rather than existing only in prose.
