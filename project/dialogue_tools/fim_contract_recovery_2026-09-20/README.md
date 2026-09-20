# Recovered production dialogue toolchain — 2026-09-20

Recovered from the user's local `_FIM_CONTRACT_REPAIR.zip` and audited against BASARA Foundry canon.

## Authority

The recovered `FIM_CONTRACT_REPAIR.py` is the authoritative Sept-14 repair implementation for the final GSM/FIM contract:

- GSM descriptor offsets/lengths are 16-bit code units.
- `0xFC0E argc=2`, `0xFC17 argc=3`, `0xFF91 argc=0`.
- `0xFFFD` delimits speeches.
- `0xFFFE` increments visual line count.
- FIM secondary `col0 = (lines << 16) | visible_glyphs`.
- FIM secondary `col1.high16 = speech start offset in GSM units`.
- Standalone repair allows only those 6 bytes per secondary row to change and reparses/revalidates the rebuilt ARC before writing.

Recovered ZIP SHA-256:
`91f304cf25cab63a929e86377ecf07fba97fb3441a3af77b1577c1b95a0f6114`

Source hashes:
- `FIM_CONTRACT_REPAIR.py` — `2dda5bcbba10d20467fe91ae9a1e3e0bc0422ab4fcb8e4e7cb2a232dca985013`
- `FIM_CONTRACT_ROLLBACK.py` — `5eff33ffdead394fdba6b5269d95d67c2cf7cfc207c63ccf504b718b9ee5771b`
- `GLUED_RUN_REPAIR.py` — `63f59e78abd4dc996f58b980aa37ce201baf2ec4eb5b26582cd1a98292ab1e50`
- `SEPARATOR_REPAIR.py` — `a19ba0d7397c743ff483032e8d9e2d3dafdf457d7468bbb38d61ecf454ce4548`
- `SCAN_TEXT_DEFECTS.py` — `bba221464414ceeb40ab5ecd82f417140555832214efb031be7552bec7587c66`

The recovered undo ledger contains original values for **1,379 archives**.

## Rollout evidence in the recovered package

`GLUED_RUN_REPORT.json` records 483 repaired archives / 1,061 inserted spaces / 30 untranslated m999 archives / 0 errors.

`SEPARATOR_REPORT.json` records 1,287 repaired archives / 1,590 separator replacements / 30 untranslated archives / 0 errors. The recovered separator source states the one-archive separator fix was hardware-proven on 2026-09-14 before rollout.

The latest FIM report showing only 45 repaired archives is a later cleanup rerun: its console says 1,334 pre-existing undo archive records were retained and 45 newly recorded, yielding the 1,379-archive ledger.

## Quarantine warning

The separately recovered loose `msg_edit.py` is **NOT** the final production writer. It still has `FC17 argc=1`, `FF91 argc=1`, says only secondary col0 is rewritten, and uses the older `groups_of()` speech model. Keep it only as provenance until it is upgraded to the recovered contract and fixture-tested.

Do not replace the recovered final grammar with the legacy Alrummi port.
