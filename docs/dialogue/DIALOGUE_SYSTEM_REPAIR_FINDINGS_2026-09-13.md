# DIALOGUE SYSTEM REPAIR FINDINGS — 2026-09-13

## Status

A production corpus repair pipeline now exists as `UTAGE_DIALOGUE_SYSTEM_REPAIR_2026-09-13.zip`.

The repair is not a blanket Japanese/SH transplant. It uses the current UPN `rom/eng/id` tree as the translation authority and same-name pristine Utage `rom/jpn/id` archives as the structural authority.

## Root cause refinement

The dialogue regression is best explained as a contract failure between English primary GSM text and FIM reveal budgets, not by row cardinality alone and not by a general primary-GSM corruption.

The old builder grouped visible runs separated by style controls as separate speeches when writing FIM secondary col0. Capcom FIM ownership is instead defined by the primary table's col4 secondary span; `FFFD` terminates a speech; `FFFE` is a line break; style controls such as `FF91/FF92` do not create another secondary speech.

For the clean m019/pl003 failure object this produces exactly three under-budget entries:

- primary 504 / secondary 160: 43 -> 59 chars
- primary 506 / secondary 162: 38 -> 50 chars
- primary 516 / secondary 171: 22 -> 25 chars

The first two occur immediately before the observed record-509 runaway.

## Reinterpretation of the earlier runtime A/B

The earlier observation that `English primary GSM + pristine FIM` runs away does not independently prove the English GSM is malformed. Pristine FIM budgets are sized for Japanese text and are often too small for English. The inverse (`Japanese primary GSM + English FIM`) is tolerant because oversized reveal budgets are benign.

This is independently supported by official Samurai Heroes English m019/pl003. SH record 509 is the official English equivalent of the exact Utage loop window, and it uses larger/multiline FIM budgets than pristine Japanese. In a 250-speech SH m019 oracle check, the new ownership/boundary algorithm had zero line-count mismatches and zero under-budget cases.

## Whole-system production rules

The new corpus tool:

- scans every live English `msg_m*_pl*.arc`;
- requires the same-name pristine Utage counterpart;
- requires matching FIM cardinality and identical FIM primary table;
- requires matching non-FFFE control opcodes AND arguments and matching FFFD speech count;
- patches only FIM secondary col0;
- makes monotonic changes only: line/char allowance can increase, never decrease;
- preserves every non-FIM raw resource exactly;
- blocks ambiguous/cardinality/control-drift archives rather than guessing;
- creates a root-ready ZIP, JSON manifest, CSV changes list, and per-ARC reports;
- includes a guarded apply workflow with SHA checks and automatic backup.

The future builder `msg_edit_system_fixed.py` also preserves trailing GSM pool padding and uses FIM ownership/FFFD semantics for budget calculation.

## Regression validation

Three independent Utage inputs were run through the production tool:

- m019/pl003: 3 monotonic repairs; output is byte-identical to the previously approved FIM-only candidate, SHA-256 `f2f576966873e82c8a1a9bdb41a6ce25d4c381596503ff038270d165394bfb06`.
- live m034/pl013: 72 monotonic repairs. Five previously proposed reductions are deliberately left untouched by production mode.
- live m045/pl013: 1 monotonic repair.

All three outputs passed the verifier with zero non-FIM raw-resource changes and no primary-GSM non-FFFE/FFFD structural drift.

## Runtime status

This is statically validated but still requires a full rebuilt-corpus cold-boot test in RPCS3. Do not call the dialogue system release-proven until a formerly failing stage passes the old runaway point and several additional missions/characters complete normally.
