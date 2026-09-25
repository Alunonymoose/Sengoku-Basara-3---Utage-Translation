# basara — the Utage patch toolchain

One library and one command for everything the English patch touches:
ARC archives, XET textures, GSM/FIM message tables, TNF/CSA fonts, PSL
layouts, translation catalogs and installs.

```powershell
# once, from the repo root (Windows or Linux, Python 3.11+)
python -m pip install -e project/basara[test]
basara --version
```

Set `ROM` to your live `...\PS3_GAME\USRDIR\nativePS3\rom\eng`.

## Translators

```powershell
basara msg tables  $ROM\tenka\equip.arc                 # which tables, which grammar, contract OK?
basara catalog export $ROM\tenka\equip.arc id_brief_r -o brief.tsv --ref $JPN\tenka\equip.arc
#   open brief.tsv in Excel / Google Sheets, fill the "translation" column
basara catalog lint brief.tsv --arc $ROM\tenka\equip.arc --table id_brief_r --budget 700 `
       --terms project\terminology\canonical_english_terminology_2026-09-24.json
basara catalog import brief.tsv --arc $ROM\tenka\equip.arc --table id_brief_r `
       --arc-path tenka/equip.arc --id brief-pass-1 --budget 700 -o brief.toml
```

Markup you will see: `{br}` new line, `{p}` next speech, `{end}` end,
`{c:3}…{/c}` coloured span, `{spk:2}` speaker. Keep every tag except `{br}`;
lint refuses anything that drops a colour span, adds a speech, uses a
character the font doesn't have, exceeds the width budget or uses a
forbidden terminology variant.

## Texture artists

```powershell
basara tex arc-list $ROM\versus\menu.arc                 # formats + byte-order verdict per member
basara tex decode  member.xet member.png                 # DISPLAY colours, what the game shows
```

Paint on a copy of that PNG. After approval, the build takes it from there.

## Engineers: build → install → rollback

A patchset (`*.toml`) is the only thing that changes game files:

```toml
schema = "basara.patchset/1"
id = "lottery-and-brief"

[[archive]]
path = "tenka/equip.arc"
sha256 = "<live sha256 it was authored against>"

  [[archive.text]]
  table = "id_brief_r"
  record = 1464
  expect = "Sacred Tree Bow: First Frost{end}"
  text = "Sacred Tree Bow:{br}First Frost{end}"
  budget = 700

  [[archive.texture]]
  member = "tenka_023_ID_HQ"
  candidate = "art/tenka_023.png"
  candidate_sha256 = "<hash of the APPROVED png>"
```

```powershell
basara build   brief.toml --root $ROM --out E:\BASARA_BUILDS\brief-pass-1
basara install E:\BASARA_BUILDS\brief-pass-1 --root $ROM --backup-root "E:\Utage Patching New\_BACKUPS" --dry-run
basara install E:\BASARA_BUILDS\brief-pass-1 --root $ROM --backup-root "E:\Utage Patching New\_BACKUPS"
basara rollback "E:\Utage Patching New\_BACKUPS\brief-pass-1_<stamp>\INSTALL_RECORD.json"
```

`build` refuses a stale patchset (live hash or `expect` changed), an
unapproved candidate (hash changed), a width overflow, a lost colour span, a
speech-count change and any FIM contract violation anywhere in the table. It
re-opens the finished ARC and re-reads every edit before writing
`build.json`.

`install` backs up every target first (verified from disk), writes
atomically only if the live file still has the build's input hash, reads
back the result and writes `INSTALL_RECORD.json`. Running it twice is a
no-op. `rollback` restores only files that still hold our output, and never
erases later edits.

Cold boot in RPCS3 is still the final gate.

## Whole-tree checks

```powershell
basara msg census $ROM --out E:\BASARA_AUDITS\msg_census.json   # every GSM/FIM: grammar + contract
basara tex census $ROM --ref $JPN --out E:\BASARA_AUDITS\xet_census.json   # legacy-encoded textures
```

See `ARCHITECTURE.md` for the design and the migration plan.
