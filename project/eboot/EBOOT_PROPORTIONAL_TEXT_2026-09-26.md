# Why Utage draws English monospace, and the one-instruction fix (2026-09-26)

Inputs (hashes; the EBOOTs themselves are not committed):
- Utage live `EBOOT.elf` (17,440,144 B, contains BLJM60389): RPCS3 PPU hash computed as `PPU-cccc7497edc2f0c81860f8e48f4fd05b652a4df3`. Check it against the RPCS3 log.
- Samurai Heroes `EBOOT.elf` (15,603,808 B): `PPU-06a41e923a3b04beac5121d0174c82bfffb8bd2a`.

## Data side (ruled out)

- SH's global ascii TNF, CSA and pages are byte-identical to the per-set copies Utage uses.
- The GSM grammar is the same, and the LSP has no pitch field (RUNTIME_ISSUES rounds 2–3).

## Code side

rFontCode in memory (from its serializer, Utage 0x140768 / SH 0xf9668):
- +0x60 glyph count;
- +0x64 cell width;
- +0x68 cell height;
- +0x6c code array (count at +4, data at +0x10).

Each Code has id +4, x +6, y +8 and **advance +0xa**.

The only glyph routine that reads the advance is Utage `0x4e8348` (SH `0x42b168`, the same code):

```
0x4e8394  bl   0x919e8          ; return obj->0x24  (mLanguage; 0 = jpn)
0x4e839c  cmpwi cr7, r3, 0
0x4e83a0  beq  cr7, 0x4e88ac    ; Japanese -> per-glyph range test
0x4e83a4  lhz  r0, 0xa(r27)     ; proportional: pen += advance * scale
...
0x4e88bc  bl   0xa7040          ; slot range test: rangeStart <= glyph <= rangeEnd ?
0x4e88cc  bne  0x4e891c         ;   yes -> proportional (advance)
0x4e88d0  lfs/fmuls ...         ;   no  -> FIXED cell pitch (the monospace)
```

- **`0x919e8` is the language getter.** It is `return this->0x24`. Its other callers compare the value with a cached language to trigger a resource reload (`0x59c68`) and test `<= 1` (`0x3daec4`).
- **`0xa7040` is the per-set range test.** It returns true when the glyph lies between `rangeStart` (+4) and `rangeEnd` (+6) of the message-set slot.
- **How the range is set** (`0xa8be8`–`0xa8c5c`): it is initialised to −1/−1, then filled with the glyph values at the first and last valid entries of that set's CSA table (128 × u16).
  - A slot whose range is not filled stays −1/−1, so every glyph in it falls outside the range and is drawn at fixed pitch.
- **SH runs the same code with `mLanguage != 0`.** It never reaches the range test, so all text is proportional. It also adds a −2 × scale tracking term (constant at −0x7fa4); Utage's proportional path adds 0.

## The fix

Make the branch at `0x4e83a0` fall through: `beq cr7, 0x4e88ac` (`0x419e050c`) becomes `nop` (`0x60000000`).

- Every glyph then uses its TNF advance, as in SH.
- Japanese fonts are unaffected in practice: their kanji advance is 26, the cell width, and half-width glyphs are 15, which is what they were designed with.
- It is shipped as an RPCS3 `imported_patch.yml` entry, toggled in the Patch Manager. `EBOOT.BIN` is not modified.

## Related data defect

These 31 per-set TNFs still carry Japanese fixed advances (Latin glyphs at 15), so their English stays evenly spaced even with the EBOOT fix:
- the move-list sets `id_skill00`–`id_skill29` (pause `waza_plNNN`);
- one `id_title` copy (`4d59c544`).

They need their glyph advances set from the ascii TNF, or their English moved onto the ascii font.

Status: **CANDIDATE**, not runtime-tested. The acceptance test is a cold boot with the patch on:
- the BASARA Mart description;
- a mission card;
- the pause stage name;
- the defeated / KO'd log.

Check each for proportional spacing, and that Japanese-only screens are unchanged.

## Real-PS3 delivery (primary route, 2026-09-26)

The live `E:\Utage Patching New\PS3_GAME\USRDIR\EBOOT.BIN` (17,442,576 B, sha256 `7d1ba4963e005549…`) is already a fake-signed SELF (key revision 0x8000):
- the ELF is stored plain at file offset 0x980;
- there is no encrypted metadata;
- the control digest is the constant make_fself value `627cb180…`, not a hash of the content.

The embedded ELF differs from the uploaded `EBOOT.elf` in 17 bytes at 0xe774f4 (an earlier project string edit, `rom\eng\title_id`). The live BIN is the base to use; the loose `.elf` is not.

Patched build:
- `EBOOT.BIN` with exactly 4 bytes changed at file offset 0x4d8d20 (ELF 0x4d83a0, vaddr 0x4e83a0): `41 9e 05 0c` becomes `60 00 00 00`;
- sha256 `e73b639778ce4f0140e89c2ec61f2e1b495b2ea3c30f72b6987cea83d396fd41`.

This works on the same PS3 setup that already runs the current fake-signed EBOOT (CFW or HEN), and on RPCS3 with no patch.yml. The RPCS3 yml is kept only as an optional alternative; its PPU hash was computed from the loose `.elf`, so it will not match the live BIN.

Install: hash-verified backup, then replace, then read back (PowerShell in the session log). Rollback: restore the backup.
