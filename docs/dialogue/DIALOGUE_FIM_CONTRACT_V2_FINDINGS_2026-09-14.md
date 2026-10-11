# Dialogue FIM Contract V2 — Cross-Stage Finding (2026-09-14)

## Material supersession

The earlier description of FIM secondary `col0` as a loose reveal "budget" and the V1 monotonic rule (raise-only) are superseded.

Cross-stage reference analysis proves a stricter packed contract.

## Exact rule

For each secondary owned by a primary GSM row:

- ownership count = next primary FIM `col4` minus current `col4`
- `FFFD` separates owned speeches
- if `FED2` occurs in a speech, pre-`FED2` low-cell data is prefix metadata and excluded from reveal metrics
- otherwise count from the start of the speech
- all reveal-body low cells `<0x8000` count, including `0x0000` spacing cells
- opaque `0x8000..0xEFFF` cells do not count
- each `FF92` contributes +1 reveal unit
- each `FFFE` contributes +1 visual line
- `col0.high16 = visual lines`
- `col0.low16 = reveal units`

## Independent reference results

Zero exceptions:
- pristine Utage m019/pl003: 513 visible owned speeches
- official Samurai Heroes m019/pl003: 250
- pristine Utage m034/pl013: 606
- official Samurai Heroes m034/pl013: 325
- pristine Utage m045/pl013: 434

This corrected two earlier incomplete assumptions:
1. m019 alone did not expose FC17's pre-FED2 prefix because those prefix cells were often zero/blank.
2. m019 alone did not prove whether zero-only runs inside reveal text count. m034 official/pristine rows prove that they do.

## Current-English defects

- m019/pl003: 3 mismatches, all reveal low16 undercounts.
- m034/pl013: 77 mismatches; 61 line high16 mismatches; 77 reveal mismatches. Five require decreases, disproving raise-only as a general repair.
- m045/pl013: 1 reveal mismatch.

The five m034 decreases occur on multi-speech rows where a prior builder placed a previous/first-speech metric into the following secondary. Examples:
- row 312: sec126 `0x0001000F -> 0x0002002B`, sec127 `0x0002002B -> 0x0001000B`
- row 1935: sec823 `0x00010010 -> 0x00020035`, sec824 `0x00020035 -> 0x00010004`
This is metric misassignment, not benign positive slack.

## Separate m005 failure class

Do not collapse the project to one dialogue bug. Existing runtime/structural evidence shows current m005/pl013 has 1966 primary rows while pristine structure records 2104. FIM V2 must hard-block such cardinality mismatch. m005 requires primary-GSM structural remapping and its own runtime proof.

## Promotion state

Metric semantics: reference/structural proof.
m019/m034/m045 candidate outputs: structurally verified.
Runtime causality: still requires m019 cumulative ladder cold boot.
Mass rollout: blocked until runtime proof + corpus scan review.
