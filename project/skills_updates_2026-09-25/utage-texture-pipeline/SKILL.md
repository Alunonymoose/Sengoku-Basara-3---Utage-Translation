---
name: "utage-texture-pipeline"
description: "Sengoku BASARA 3 Utage texture/atlas work (TEX/XET, BC3, PSL/LSP). Covers the format contract (standard BC order, 0x2A YCbCr), the canonical utage_xet codec, where the tools live, the candidate/approval gate, block-graft encode, ARC rebuild and validation."
---

# Utage — texture / atlas pipeline

Start with **utage-session-start** (authority, routing, install protocol).

The E: `.claude/skills/basara-texture-engineering`, `basara-production` and `basara-arc-engineering` skills define the process gates. Read them fresh; they win on process. This skill adds the format facts, the tool locations and the live conflicts. On format facts it supersedes older notes, including the format line in utage-menu-arc-texture-job.

## 1. XET contract (STRUCTURALLY VERIFIED unless noted)

**Header.** Magic `\0XET`, big-endian.
- texFlags u32 at +0x08: `mip = v & 0x3F`, `w = (v >> 6) & 0x1FFF`, `h = (v >> 19) & 0x1FFF`
- Format id: byte at +0x0E
- Mip offset table: u32 BE absolute offsets at +0x10. One-mip payload starts at 0x14.

**Formats** (live census 2026-09-25, ENG: 0x2A 49,793 · 0x17 419 · 0x19 75 · 0x15 36 · 0x27 19 · 0x2B 0):

| Format | Storage |
|---|---|
| 0x2A / 0x17 / 0x18 | BC3/DXT5 |
| 0x19 | BC1 |
| 0x15 | BC2/DXT3 (read/preview only) |
| 0x27 | A8R8G8B8, stored A,R,G,B |
| 0x2B | RBxG; never seen in Utage, writing blocked |

**BC payload byte order: STANDARD (RUNTIME PROVEN 2026-09-25).** Only the XET container is big-endian. Inside BC blocks everything is standard DXT order: RGB565 colour endpoints are **little-endian u16**, same as PC. The 2026-09-23 "PS3 big-endian endpoint" rule is DISPROVEN (title_004 runtime 2026-09-18/24; menu.arc member 58 runtime 2026-09-25; Alrummi3 2026-09-10). Never byte-swap endpoints.

**Write-enabled:** BC3, single mip, swizzle 0. Everything else fails closed: multi-mip, non-zero swizzle, BC1/BC2 writes, 0x2B, unknown formats.

**Layout (PSL/LSP v0x21):**
- 0xB0-byte node records; count at header +0x0C.
- Destination rect at +0x74..+0x80; source min/max at +0x84..+0x90.
- `_ID_HQ` textures = 2× the SD PSL coordinates per axis (fixture-proven, not universal).

## 2. 0x2A colour semantics: RESOLVED (RUNTIME PROVEN)

Every 0x2A texture is BC3 (standard order) **plus** the Kuriimu2 PS3 YCbCr shader: stored `(Cr, A, Cb, Y)`, neutral chroma 123.
- Write: `Y=.299R+.587G+.114B`, `Cb=123-.168736R-.331264G+.5B`, `Cr=123+.5R-.418688G-.081312B`, stored `(Cr, A_in, Cb, Y)` (truncate + clamp, like C# `(int)`).
- Read: `alpha=G`, `Y=A`, `Cb=B-123`, `Cr=R-123`, `R=Y+1.402Cr`, `G=Y-.344136Cb-.714136Cr`, `B=Y+1.772Cb`.
- Proof: title_004 (2026-09-18) and menu.arc member 58 (2026-09-25: the xetenc build showed navy (8,63,140), predicted (0,56,132); standard order puts the JPN original's chroma exactly on 123).
- Why "plain looked right": xet3/xetenc read endpoints **swapped** and skipped the shader. That combination happens to look like a legible picture. It is not what the game renders.
- Candidates, previews and boards are always **display RGBA** from `utage_xet.decode_display()`. Only the codec touches stored channels.
- A magenta/green/cyan cast on new lettering = wrong writer. STOP. (The user's approved `cp_name_pl` art is the exception: leave it alone.)
- title_004's transparent-texel prefill colour is artwork-specific; `utage_xet` defaults to `--prefill dilate`.

**Legacy damage.** Anything written with `xetenc.py` (since 2026-09-23: waza2/result_id labels 2026-09-24, menu.arc member 58 v1/v2) is probably mis-coloured in game. Find it with `xetcli.py census <rom/eng> --ref <rom/jpn>`; repair by recovering the art with `utage_xet._legacy_view` and re-grafting with the certified writer (backup/approval/cold-boot gates apply).

## 3. Tools

| Role | Location / API |
|---|---|
| **Canonical read/write (Python)** | GitHub `project/texture_tools/utage_xet/utage_xet.py` (`xet_info`, `decode_display`, `decode_storage`, `graft`, `byte_order_evidence`, `scan_against_reference`) + `xetcli.py` (`info`, `decode`, `graft`, `arc-list`, `arc-graft`, `scan`, `census`). 22 tests incl. display-space colour regression. `graft` compares against the live **display** decode, re-encodes only changed 4×4 blocks, refuses swapped/legacy targets, uncertified formats, multi-mip and swizzle. `arc-graft` rebuilds through pinned safe_arc, re-extracts, writes `*.final_display.png` + `*.record.json`. |
| Release-audit decoder | `project/texture_tools/xet_recovery_2026-09-23/foundry_xet_decoder_20260923.py` (corrected to standard order 2026-09-25; parity-tested with utage_xet) |
| Canonical C# writer | Foundry `UtageXetCodec` / `UtageBc3BlockGraft` / `UtageSingleEntryXetGraft` (swap removed 2026-09-25; default base = current live target; `--base-mode restore` for explicit pristine restores). Needs CI build via PR before production use. |
| **QUARANTINED — never write with** | `xetenc.py`, `xet3.py`, `validate_xetenc.py` (E: `_codex_tenka_v6\xetenc_RECOVERED_2026-09-24\`, Drive). SOL6 `xet_bc3_patch.py`/`xet_solved_read.py` (E: only): endpoint order and 0x2A handling unverified — do not use for 0x2A until checked against `utage_xet`. |
| ARC | `safe_arc.py` (pin `7beb24a5…`: `parse_arc`, `rebuild_arc`, `verify_rebuild`), or `arc_tools.py` |
| PSL/layout inspectors | E: `_SOL6_20260923\tools\inspect_psl_nodes.py`, `inspect_kessen_layout.py`; Foundry PSL reader (typed dest/src rects) |
| Owners / donors | Resource Ownership Analyzer; Donor Matcher V5.1; `UTAGE_PIPELINE_MANIFEST.json`; Foundry snapshot SQLite |
| Visual census | `project/tools/release_audit_2026-09-24/texture_review_export.py` (uses the corrected decoder; display space) |

Requirements: Python 3.11, numpy, Pillow. Fonts on the laptop are in `C:\Windows\Fonts`. The cloud has DejaVu; install others if the style needs them.

## 4. Candidate stage (stop at approval)

1. **Live input.** Hash the live ARC and parse it. Extract the member by index and path. Note its format, dimensions and mips.
2. **Ownership.** Enumerate every provider of the exact (type hash, lowercase path). Co-resident proven-equivalent duplicates form one lockstep set (e.g. `waza2_001/_029` live in both `select/c_common.arc` and `c_versus.arc`; `tenka_023/024` in both `equip.arc` and `smith.arc`).
3. **Donor before art, in this order:**
   1. An exact compatible SH donor (Donor Matcher V5.1)
   2. An approved Utage English sibling
   3. Text already translated elsewhere, re-rendered (e.g. `waza2` was a line-subset of `waza_name_pl`)
   4. Only then custom art
4. **Wording.** Use the terminology JSON; SH official wording wins. Known open item: Faizlie Muto vs Fairy Muto.
5. **Masks.** Prove the consumed region from PSL/LSP. Japanese in unused or support atlas areas is not a target. Freeze source-space masks and expand them to 4×4 blocks.
6. **Isolated art only.** Composite deterministically onto a **copy of the live decoded sheet**. The live target is the base; pristine JPN is used only for an explicit, auditable restore. Never have an image model generate a whole sheet, a reference or the board.
   - Proven lettering method (2026-09-24 result_id/waza2):
     - Detect per-line alpha bands and sample each band's median RGB under alpha > 200.
     - Render with auto-fit font size and a matching glow.
     - Re-implement the helpers if they aren't on E:.
7. **Checks.**
   - Pixel identity outside the masks. If it fails, reject.
   - Reject weak candidates yourself.
   - Write `candidate_manifest.json`: source ARC SHA, member index/path, member SHA, reference SHA, dimensions/format, masks, `byte_order_evidence` verdict, candidate PNG SHA, `unchanged_outside_mask: true`, `approval_required: true`, `arc_patched: false`.
   - Build a deterministic board: real current + real reference + exact candidate.
8. **STOP** for user approval.

## 5. After approval (pixels frozen)

1. Encode with `xetcli.py arc-graft` (or the corrected Foundry C#). Graft only the touched blocks; the target XET shell and untouched blocks stay byte-identical.
2. Rebuild only the budgeted members, applying the same final XET to every lockstep provider.
3. Reparse the finished ARC, re-extract, and decode the stored member.
4. Compare against the approved PNG, reporting collateral inside touched blocks.
5. Check that protected members are byte-identical.
6. **Second approval:** show the final decode taken from the rebuilt ARC.
7. Install on live E: per utage-session-start §6 (verified backup first; never a ROOT-READY ZIP).
8. Add or update the runtime-matrix row and state the exact screen to cold-boot.

## 6. Current texture queue (verify against live E: first)

**Open**
- BASARA Lottery `tenka_023_ID_HQ` (512², 0x2A) / `tenka_024_ID_HQ` (1024×512, 0x2A) in both `tenka/equip.arc` and `tenka/smith.arc`. No SH donor exists, and the previous candidate was rejected.
- `cp_name_nak_009..027`, `cp_name_pl_100..106`
- Chapter gold badge (`select/c_story.arc` `charasele_story` node 251 is a dynamic `dummy_BM` text field over node 246's brush art)
- Green shop icon
- Kojuro purple strip
- 36 divergent texture keys
- Versus `menu.arc` quality pass. Member 58 v3 (standard order + YCbCr) installed 2026-09-25 (live `ee9b0da1…`); cold boot to confirm colours and whether the button labels' own dark plate doubles the game plate.
- Census + repair of every texture written by the legacy xetenc path (see §2).
- "Sengoku History" logo overlap (likely a texture)
- Hard proof that the locked Mart marker renders `???`

**Closed (runtime pending)**
- `waza2_000..029`
- `tenka/waza_name_pl016..029`

**Not targets**
- `shigen_000..004` are language-neutral.
- `tenka_022` is a decorative frame. The old 運UP claim is disproven.

## 7. Disproven: don't revive

- XET as Exient/XGS
- The raw-YUV / half-dimension / Morton reading
- Blanket 8×4 swizzle
- 16-byte ARC entries (they are 80 bytes: 64-byte name + type, comp size, packed = `raw<<3|flags`, offset)
- Pristine JPN as the default base
- Matching-name SH transplants
- "The ARC containing it = the owner"
- Validating only the pre-encode PNG
- PS3 big-endian BC RGB565 endpoints (disproven at runtime 2026-09-24/25)
- 0x2A "plain" (no-shader) reading; xetenc/xet3 as a write path
- Identity patches or encoder→own-decoder round trips as "validation"
- Generic PS3 zlib window 14 (Utage uses CMF 0x78, window 15)
- `rArchive` entries as nested ARCs (they are SCRA child manifests)