# Runtime-proven PS3 XET path — 2026-09-25

This folder is the durable copy of the runtime-proven Utage PS3 XET path recovered and validated on 2026-09-25.

## Operational rule

- BC colour endpoint words use standard DXT little-endian RGB565 order.
- XET/container header integers remain big-endian where defined.
- 0x2A = BC3 plus Kuriimu2 YCbCr display/storage transform: stored `(Cr, alpha, Cb, Y)`, neutral chroma 123.
- 0x17/0x18 = plain BC3.
- 0x19 = BC1 read.
- 0x15 = BC2/DXT3 read only.
- Production writes are fail-closed to supported single-mip/swizzle-0 BC3 fixtures.

`xet_ps3.py` is the public entry point. `xet3.py` and `xetenc.py` are legacy internal bridge dependencies only; do not call them directly for production.

## Pinned hashes

- `xet_ps3.py`: `4840efade14090061ed0dc87004aadec509bb1982af866cceb337bae5260debb`
- `xet3.py`: `236916ad85c564209867da5626c6e4f494686604b53b1243d3070eb9ce1db54a`
- `xetenc.py`: `a23b1b6b0c7d76b6fe0911f76fff698f3a42609849f0ea2ceee31890ef310489`

The older `project/texture_tools/xet_recovery_2026-09-23/foundry_xet_decoder_20260923.py` is historical/disproven for endpoint order and must not be used as current production or review authority.
