# Utage dialogue V18 addendum — 2026-08-31

This addendum supersedes the V17 dialogue-window conclusion in
`HANDOVER_UTAGE_2026-08-31.md`.

## Live state

- V15 mission-local ASCII/message repair: installed and retained.
- V16 Western message/banner node geometry: installed and retained.
- V17 ordinal animation splice: removed; its name-to-block mapping was invalid.
- V18 vertical alignment: installed in both live `rom/eng/id/cockpit1P.arc` and
  `rom/jpn/id/cockpit1P.arc`; offline validation passed; cold-boot runtime test required.

Mirrored live cockpit SHA-256:

`888078d0cfc7fdba2033c0feb17a552a3a1f450d5de529fafbbc51b47878edd6`

## Correct diagnosis

`title_id.arc` and `basara.arc` do not own the in-battle dialogue controller.
The relevant resource is `id\\lsp\\jpn\\cockpit\\cockpit` in `cockpit1P.arc`;
Samurai Heroes' donor is `id\\lsp\\abr\\cockpit\\cockpit`.

The screenshot line is m034/pl015 GSM record 501, FIM message ID 189. Its SH
FIM44 record has line count 2 and character count 50, so the repaired message
system is selecting a normal two-line dialogue page correctly.

The earlier V17 parser assumed each animation-table name had a one-to-one
boundary block. That is false: the table has name-only entries, so ordinal
alignment drifts. The byte range V17 labeled `Ani 0_0_2` actually targeted
unrelated stable node IDs (Meter_G, Kamon, BasaB, 0_0_3 and Kao_K), not the
dialogue window. V18 starts from `V17_BACKUP_cockpit1P_pre_v17.zip` to remove
that splice.

Animation blocks must be identified by stable node ID:

- ID 182 `Mess1`: three long-window blocks; already exact SH.
- ID 77 first `Line_U`: three line-layout blocks; already exact SH.
- ID 76 `3_1`: two text-container blocks; already exact SH.
- ID 72 `3_0`: two dialogue-root blocks; these were the remaining mismatch.

V16 installed SH's base `3_0` node Y position, but both animated states still
used Utage's Y = -2.0. V18 changes four f32 keys (two per block) to SH's Y =
3.0. Only eight raw bytes differ from the clean pre-V17 LSP, and only ARC entry
18 changes. The LSP stays 91,480 bytes and the archive stays at 39 resources.

## Files

- Builder: `build_v18_dialogue_alignment.py`
- Safe runner (resolves the duplicate `Line_U` names by stable ID 77):
  `run_v18_dialogue_alignment.py`
- Validation: `V18_DIALOGUE_ALIGNMENT_VALIDATION.json`
- Pre-V18 runtime backup: `V18_BACKUP_cockpit1P_pre_v18.zip`
- Root-ready package:
  `Utage_Battle_Dialogue_V18_VERTICAL_ALIGNMENT_ROOT_READY.zip`
- Package SHA-256:
  `e78eb92ad1dbfffe2b5f17be51a83fcaeba963bc9d14927e2f5dd09d246e4f32`

Independent audit: ZIP CRC passed; four package members; both packaged ARCs are
byte-identical to the live files; ENG/JPN are byte-identical; only entry 18
differs from the pre-V17 V16 archive; all ARC members decompress. The legacy
`id\\dummy_BM` declared-size mismatch is byte-identical to the pre-V17 baseline
and is not a V18 regression.

## Runtime test

Fully close RPCS3 and cold boot; do not use a save state.

1. Load m034/pl015 and trigger Katakura's record-501 line: "This castle will be
   the cornerstone of our defense." Confirm the two text lines are vertically
   centered in the panel.
2. Trigger a three-line page and confirm the panel expands without clipping.
3. Check speaker name, portrait, health/Basara meters, partner HUD, KOs counter,
   mission banner and one-line dialogue for regressions.
4. Split-screen remains outside this V18 change; `cockpit2P` was not modified.
