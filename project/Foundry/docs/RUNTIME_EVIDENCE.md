# Runtime evidence and RuntimeVerified

Foundry deliberately separates **production-write proof** from **runtime proof**.

A verified ARC build proves that Foundry produced the requested bytes safely. It does **not** prove that those bytes render correctly in RPCS3 or on hardware. `RuntimeVerified` therefore requires a second, build-bound evidence transaction.

## Required evidence

`RuntimeVerificationEvidence` schema 1 records:

- runtime name (`RPCS3` for the current Utage vertical slice)
- deterministic build ID derived from the output ARC SHA-256
- full output ARC SHA-256
- screenshot SHA-256
- project-relative screenshot path
- capture timestamp
- optional operator notes

The build ID is informational convenience. The full output ARC SHA-256 remains the authoritative binding.

## App workflow

After a production texture transaction passes and the physical output ARC is re-hashed against its audit:

1. Foundry moves the asset to the **Built** stage, not RuntimeVerified.
2. The production button becomes **Attach RPCS3 verification screenshot**.
3. Before opening the picker, Foundry re-hashes the ARC and refuses stale/missing output.
4. The operator selects a PNG/JPEG screenshot.
5. Foundry re-hashes the ARC again after the picker returns.
6. The screenshot is hashed and displayed with the exact build ID + ARC SHA-256.
7. The operator must explicitly attest that the screenshot shows this exact Foundry build running correctly in RPCS3.
8. Foundry re-hashes the ARC a third time after the review dialog.
9. Screenshot bytes are persisted content-addressed under `runtime-evidence/<build-id>/` and re-verified from disk.
10. `RuntimeVerificationGuard` validates runtime, build ID, ARC hash and screenshot hash, then permits only the `Built -> RuntimeVerified` transition.
11. `runtime-evidence.json` is persisted and reloaded/revalidated before the UI reports Runtime Verified.

Any ARC mutation, mismatched build ID/hash, screenshot byte change, wrong runtime, absent evidence, or attempt to skip the Built state fails closed.

## Important limitation

Foundry does not infer from screenshot pixels that RPCS3 was actually running the named ARC. The final click is an explicit operator attestation, made safer by binding that attestation to immutable hashes and showing the selected screenshot in the confirmation dialog.

A real roulette RuntimeVerified result must not be claimed until the actual production ARC is installed/tested and an in-game screenshot is attached to that exact output hash.
