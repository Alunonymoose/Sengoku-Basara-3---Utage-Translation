# Utage Donor Matcher V5.1 — Foundry Verified — 2026-09-23

Production donor discovery / planning tool for the Sengoku BASARA 3 Utage English patch.

## Status

This package is the DeepSeek V5 implementation after Foundry-side verification and one test-fixture correction.

Verified locally against the real current `safe_arc.py`:
- **60/60 tests pass**.
- `--smoke-arc` successfully parses all nine currently mounted live-root ARCs.
- Full enrichment successfully processed the current 9-ARC / **1,038-resource** analyzer snapshot.
- Existing stored/expanded hashes agreed for all records that already had hashes.
- All encountered rTexture members in that snapshot successfully received XET header/shell enrichment.

## Files

- `utage_donor_matcher_v5.py` — matcher / enrichment / plan generator.
- `safe_arc.py` — pinned production ARC parser/writer used by this verified package.
- `test_utage_donor_matcher_v5.py` — 60-test suite.
- `PYTEST_OUTPUT.txt` — actual local pytest result.
- `REAL_CURRENT_ROOT_SMOKE.json` — smoke results for nine current root ARCs.
- `REAL_CURRENT_ROOT_ENRICHMENT.json` — 1,038-resource enrichment verification.
- `SHA256SUMS.json` — package hashes.

## What was corrected after DeepSeek V5

The sole failing DeepSeek test marked arbitrary `hello world` bytes as an `rTexture`, then expected texture enrichment not to parse it as XET. The test was corrected to use a non-texture resource type so it actually tests the intended `safe_arc` decoded-length-warning behavior.

The test helper was also corrected so a real importable `safe_arc.py` is preferred instead of always installing its test double.

The production module retains DeepSeek V5's architecture. Two tiny auditability cleanups were made:
- removed a dead `if False` bridge-call expression;
- preserve `safe_arc` codec/warning/flags metadata during enrichment.

## Production rule

Run donor discovery first. `HARNESS_READY_SAME_KEY` output can be staged through the existing donor transaction harness. Cross-key candidates remain payload-graft candidates and must not be fed directly to `donor_transaction.py`.

This tool does not mutate game files by itself.