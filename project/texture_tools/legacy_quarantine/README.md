# Quarantined texture tools — do not use for writing

| Tool | Where it lives | Why quarantined (2026-09-25) |
|---|---|---|
| `xetenc.py` (SHA-256 `a23b1b6b0c7d76b6fe0911f76fff698f3a42609849f0ea2ceee31890ef310489`) | Drive `05 Tools & Automation / 2026-09-24 — xetenc.py RECOVERED and VALIDATED`; E: copies | `patch_xet` accepts 0x2A/0x17/0x15 as one family and BC3-encodes **display RGBA** with **big-endian** endpoints. For 0x2A the game reads those bytes as (Cr, alpha, Cb, Y) in standard order, so new lettering renders magenta/cyan/green. Its validation only proved identity patches and self-round-trips. |
| `xet3.py` (SHA-256 `236916ad85c564209867da5626c6e4f494686604b53b1243d3070eb9ce1db54a`) | same folder | Decodes endpoints big-endian and returns 0x2A storage channels as if they were display RGBA. Output happens to look legible, which hid the bug. |
| `validate_xetenc.py` | same folder | Validates only structure (identity, spillover), never display colour. |

Replacement: `project/texture_tools/utage_xet/` (`utage_xet.py`, `xetcli.py`).
The legacy reading is still available as `utage_xet._legacy_view` so that
art written by these tools can be recovered and re-encoded correctly.
