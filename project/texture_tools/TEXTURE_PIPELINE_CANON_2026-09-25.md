# Utage texture pipeline — canon (2026-09-25)

**This document supersedes every earlier statement about XET BC endpoint byte
order, `xetenc.py`/`xet3.py`, and "0x2A is BC3" wording.** Older notes stay
for provenance; where they disagree with this page, this page wins until newer
runtime evidence says otherwise.

## 1. The rule, in one line

XET **container** fields are big-endian. The BC **payload** is standard DXT
byte order (RGB565 endpoints little-endian, exactly as on PC). Format `0x2A`
additionally stores the Kuriimu2 PS3 YCbCr representation inside BC3:
stored RGBA = `(Cr, alpha, Cb, Y)`, neutral chroma 123. Artists and tools work
in **display RGBA**; only the codec touches stored channels.

## 2. Format table (enforced by `utage_xet.FORMATS`)

| XET id | Storage | Display semantics | Read | Write | Status |
|---|---|---|---|---|---|
| 0x13 / 0x14 / 0x19 | BC1 | ordinary | yes | **no** | read only |
| 0x15 | BC2 / DXT3 | ordinary | yes | **no** | real fixture (result_id member 60); write uncertified |
| 0x17 / 0x18 | BC3 / DXT5 | ordinary RGBA | yes | yes | software/fixture; needs a runtime fixture |
| 0x27 | A8R8G8B8 | ordinary | yes | **no** | read only |
| **0x2A** | BC3 / DXT5 | **PS3 YCbCr shader** | yes | yes (YCbCr writer only) | **RUNTIME PROVEN** (title_004, menu.arc member 58) |
| 0x2B | BC3 / DXT5 | YCbCr + RBxG base/mask | yes (preview) | **no** | write blocked |

Always refused: unknown ids, swizzle ≠ 0, multi-mip writes, resources with
trailing data after the top level.

Texel order inside each 4×4 block is standard row-major. (The Kuriimu2
`BcSwizzle` bit coordinates `[(1,0),(2,0),(0,1),(0,2)]` describe exactly that
ordinary block layout; they are not an extra transform.)

## 3. Evidence chain (why the old "PS3 big-endian endpoint" rule is dead)

| Date | Evidence | Result |
|---|---|---|
| 2026-09-10 | Alrummi3 handoff | byte-swapping RGB565 endpoints "produces visibly corrupt output" |
| 2026-09-18 | `title_004_ID_HQ` 0x2A Sengoku logo, standard BC3 + YCbCr (Kuriimu2/BCnEncoder) | **runtime verified, user approved** (`.agents/skills/basara-utage-texture-engineering/TITLE_0x2A_RUNTIME_VERIFIED_2026-09-18.md`) |
| 2026-09-23 | xet3/xetenc session declares endpoints big-endian; decodes 0x2A without the shader | swapped + no-shader output *looks* legible, so the error went unnoticed |
| 2026-09-24 | Foundry C# adds a PS3 endpoint swap (commit series before e6ad054) | title_004 runtime failure: green rectangle, magenta logo |
| 2026-09-24 | hotfix branch `hotfix-title004-bc-endian-20260924` removes the swap | never merged into `foundry-v0.1` (orphan history); swap remained on the primary branch |
| 2026-09-25 | menu.arc member 58 written with xetenc (swapped + no shader) | in-game navy plate (8,63,140); model predicts (0,56,132) for that writer. Standard order decodes the JPN original with chroma exactly on 123. v3 rebuilt with standard order + YCbCr and installed (live `menu.arc` `ee9b0da1…`, backup `_MENU58_LABELS_V3_BACKUP_2026-09-25\`) |
| 2026-09-25 | this branch | swap removed from C# (hotfix ported), Python review decoder corrected, canonical `utage_xet` codec with in-game colour regression tests |

Why it survived: an identity patch never calls the encoder, and a writer
tested with its own decoder agrees with itself. Only a display-space test
against the game's shader, or a cold boot, catches it.

## 4. Canonical tools

| Need | Tool |
|---|---|
| Read/decode/write XET (Python) | `project/texture_tools/utage_xet/utage_xet.py` (`decode_display`, `decode_storage`, `graft`, `byte_order_evidence`, `scan_against_reference`) |
| CLI incl. ARC graft + re-extract | `project/texture_tools/utage_xet/xetcli.py` (`info`, `decode`, `graft`, `arc-list`, `arc-graft`, `scan`, `census`) |
| C# production codec | `project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetCodec.cs` (standard order, BCnEncoder.Net 2.2.1) |
| Release-audit decoder (pinned) | `project/texture_tools/xet_recovery_2026-09-23/foundry_xet_decoder_20260923.py` (corrected; parity-tested against `utage_xet`) |
| ARC parse/rebuild | `project/tools/donor_matcher_v5_1_2026-09-23/safe_arc.py` pin `7beb24a5…f6f3` (xetcli enforces the pin) |

**Quarantined — do not use for writing:** `xetenc.py` and `xet3.py`
(Drive `05 Tools & Automation / 2026-09-24 — xetenc.py RECOVERED and
VALIDATED`, E: copies). `xetenc.patch_xet` writes display RGBA straight into
0x2A with swapped endpoints; `xet3.decode` returns swapped storage channels.
See `project/texture_tools/legacy_quarantine/README.md`.

## 5. Production workflow (unchanged gates, corrected codec)

1. Re-hash the live ARC; record `mtimeMs`.
2. `xetcli.py arc-list` → confirm format, mips, swizzle, `byte_order_evidence.verdict == "standard"`.
   A `swapped` verdict means the member was written by the legacy tool: repair it first.
3. `xetcli.py decode` → display PNG. Check it against the JPN decode/runtime screenshot. A magenta/green/cyan cast is a STOP.
4. Author the candidate on a copy of that display PNG (proven edit region only). Approval gate on the exact candidate.
5. `xetcli.py arc-graft <arc> <member> <candidate.png> <out.arc> [--mask m.png] [--prefill dilate|colour --colour R,G,B]`
   → only changed 4×4 blocks re-encoded; untouched blocks byte-identical; ARC rebuilt with safe_arc; member re-extracted and decoded (`*.final_display.png`); `*.record.json` written.
6. Second approval on `final_display.png`. Patch co-resident duplicate providers in lockstep.
7. Backup → install → read-back per the install protocol. RPCS3 cold boot is the final gate.

Transparent texels: `--prefill dilate` (default) fills hidden RGB under
alpha 0 from the nearest visible colour so BC endpoints are not dragged to
black. title_004 used a fixed colour (`--prefill colour --colour …`); choose
per asset and record it.

## 6. Repairing textures already written with the legacy tool

Suspects: everything written with `xetenc.py` since 2026-09-23 (e.g. waza2
and result_id labels 2026-09-24) and any other path that swapped endpoints.
Codex's SOL6/quest builders pack endpoints with `'<HHI'` (standard order);
check whether they applied the 0x2A shader before assuming they are clean.

Run locally (read-only):

```bash
python project/texture_tools/utage_xet/xetcli.py census "E:/Utage Patching New/PS3_GAME/USRDIR/nativePS3/rom/eng" \
  --ref "E:/Utage Patching New/PS3_GAME/USRDIR/nativePS3/rom/jpn" --out E:/BASARA_AUDITS/xet_census.json
```

Each flagged member lists the changed blocks whose **legacy reading** fits
the untouched art far better than the certified reading. Repair = decode the
member the legacy way to recover the approved artwork
(`utage_xet._legacy_view`), graft it back with the certified writer, then
the normal approval/backup/install/cold-boot gates.

## 7. Evidence levels

`utage_xet` tests are SOFTWARE/FIXTURE proof (22 tests, CI). 0x2A standard
order + YCbCr is RUNTIME PROVEN on two real fixtures. BC2 read, and BC1/0x17
write, are not runtime-certified. The Python BC3 encoder is a
PCA/least-squares fit, not bit-identical to BCnEncoder.Net; RGB565 expansion
uses bit replication (assumed to match BCnEncoder; C# parity not yet
verified offline — within ±1 level).
