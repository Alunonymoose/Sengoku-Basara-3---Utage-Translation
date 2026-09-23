# XET solved-tool recovery — 2026-09-23

This folder preserves a reconstructed **read-only** implementation of the solved 2026-09-23 PS3 XET contract.

It does **not** claim to recover the missing production encoder `xetenc.py`.

Evidence:
- source SHA-256: `d0ffe59abd91fa18bd5ec76bdf8d73fbe7595597b4f7ab3339a5d5de7fc58255`
- local validation record SHA-256: `09d429c8e9c357cb57a93cf3a866eb0752595d8f5ff1bc1226b240d86b94b626`
- 654 XET resources in `UTAGE_SOL6_2026-09-23_ROOT_READY.zip` passed header/payload validation with 0 errors
- four real 512x512 0x2A surfaces were fully decoded.

The complete original solved-XET evidence separately records a 2,516/2,516 decode sweep.

**P0 still open:** recover/port a production block-level encoder, prove identity patch byte-exactness, changed-block correctness, ARC rebuild/re-extract, untouched-block preservation and runtime fixture before declaring the custom write path future-proof.
