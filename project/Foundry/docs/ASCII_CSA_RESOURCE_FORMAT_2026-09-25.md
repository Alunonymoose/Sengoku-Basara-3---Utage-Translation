# rAscii / CSA resource format — Utage live-corpus proof — 2026-09-25

## Why this matters

Several files under paths containing `msg\ascii` have historically been discussed together as "ASCII resources", but the live ARC type hashes prove that they are different MT Framework resource classes with different binary contracts.

Typed identity wins over path naming.

## Resource-class mapping

Observed directly in current Utage ARC v8 bundles and cross-resolved with the SB3 resource-class table:

| On-disk magic | Resource class | Type hash | Role supported by structure |
| --- | --- | ---: | --- |
| `\0TNF` | `rFontCode` | `0x1D609FFB` | local font/glyph-code data |
| `\0GSM` | `rMessage` | `0x10C460E6` | message payload |
| `\0FIM` | `rMessageInfo` | `0x2EA515BF` | message metadata/info |
| `\0CSA` | `rAscii` | `0x5E0EF076` | 7-bit code -> local glyph-index map |
| `\0XET` | `rTexture` | `0x241F5DEB` | texture/font page |
| `\0TLP` | `rPalette` | `0x619CF7E7` | palette-class resource; distinct from rAscii |

Do not infer a class from a filename suffix such as `_ID_HQ` or from the directory name `ascii`.

## rAscii / CSA binary layout

All 2,037 rAscii instances seen in the current on-disk ENG ARC corpus decode to exactly 264 bytes and share this outer structure:

```text
0x000  char[4]  magic: 00 43 53 41  ("\0CSA")
0x004  u32 BE   field observed as 0x00000064 in every fixture
0x008  u16 BE   map[128]
```

Total size:

`8 + (128 * 2) = 264 bytes`

The semantic name of the 32-bit header field at `0x04` is **unknown**. The observed value `100` must not be relabelled as a count/version without further evidence.

Each map slot corresponds structurally to one 7-bit codepoint index `0x00..0x7F`.

Observed conventions:

- `0xFFFF` = unmapped / unavailable in the local glyph set.
- Any other u16 is a local glyph index.
- sparse local-font bundles map only the codepoints required by that font/resource family.
- the dominant general ASCII table is dense across ordinary printable characters except for one deliberate gap.

## Dominant general ASCII table

Across the current on-disk ENG corpus:

- rAscii instances: 2,037
- unique decompressed CSA payloads: 16
- dominant payload occurrences: 2,003

In the dominant table:

- codes `0x00..0x1F` are `0xFFFF`;
- code `0x20` (space) maps to glyph index 0;
- codes then map densely upward;
- code `0x26` (`&`) is deliberately `0xFFFF`;
- code `0x27` maps to glyph 6 and the dense sequence continues;
- code `0x7E` maps to glyph 93;
- code `0x7F` maps to glyph 94;
- total mapped slots: 95.

The absence of `&` is a strong clue that the message/parser layer may reserve that code, but **the control semantics are not proven**. No public rAscii implementation or current project script was found that names an ampersand control rule. Keep this as a hypothesis until executable/runtime evidence establishes it.

## Sparse variants

The non-dominant CSA payloads are still 128-slot maps with the same header. They appear in local baked-font bundles such as skill/title resources and contain many `0xFFFF` slots with a smaller set of glyph indices.

That supports the bounded interpretation:

> rAscii / CSA maps character-code slots to glyph indices available in the companion local font resource set.

It does not by itself prove how the engine tokenizes every GSM control code.

## Engineering rules

For message/font work:

1. Resolve resources by class hash and binary contract, not by path text alone.
2. Treat `rAscii/CSA`, `rFontCode/TNF`, `rMessage/GSM`, `rMessageInfo/FIM`, `rTexture/XET`, and `rPalette/TLP` as separate resources.
3. Preserve all 128 CSA slots unless the edit explicitly changes character coverage.
4. Preserve unknown header field `0x04`.
5. Do not silently make `0x26` drawable; its deliberate unmapped state requires parser/runtime evidence before alteration.
6. When a local font bundle changes glyph order, update the code->glyph map only with a proven companion TNF/XET relationship.

## Corpus-count caveat

The 2,037-instance count comes from the current on-disk ENG tree, which also contains some backup/test-labelled ARC copies. The binary-layout conclusion is unaffected because every observed rAscii payload obeyed the same 264-byte contract; use a runtime-path-filtered census for release inventory counts.
