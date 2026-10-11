# Dialogue repair V2 supersession notice

Do **not** treat the existing V1 `repair_dialogue_system.py` raise-only/monotonic FIM writer as production-final.

Cross-stage validation on 2026-09-14 proved that FIM secondary `col0` is an exact packed contract, not a loose lower-bound budget:

- high16 = visual line count
- low16 = reveal units
- FFFD separates owned speeches
- FED2 restarts reveal accounting after FC17 prefix metadata
- low cells `<0x8000` inside reveal text count, including zero-valued spacing cells
- opaque `0x8000..0xEFFF` cells do not count
- FF92 adds one reveal unit
- FFFE adds one visual line

Reference validation is zero-exception on pristine Utage m019/m034/m045 and official Samurai Heroes m019/m034 fixtures.

The old monotonic policy is specifically disproven by m034: five valid repairs require decreasing a misassigned secondary metric. Use the V2 implementation from the project artifact `UTAGE_DIALOGUE_FIM_CONTRACT_V2_2026-09-14.zip` until the repository implementation is replaced with the V2 writer.

Hard gate: bundles with cardinality/control drift, including the known m005 reduced-primary-GSM class, must be blocked rather than passed through FIM repair.

Runtime promotion remains pending the cumulative m019 cold-boot ladder.
