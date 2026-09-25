# BASARA binary specifications

These Kaitai Struct files are independent, read-only structural descriptions of proven portions of Utage formats.

They are **verification/research fixtures**, not replacement production writers. The current safe ARC writer and Foundry XET codec remain authoritative for mutation until generated parsers are parity-tested against the real corpus.

Current specs:

- `arc_v8.ksy` — ARC v8 header, 0x50 entry records, packed-size split and stored-payload addressing.
- `xet_v097.ksy` — XET header, packed mip/width/height fields, format byte and mip-offset table.

Open/unknown format regions must remain absent or explicitly documented rather than guessed into these specs.
