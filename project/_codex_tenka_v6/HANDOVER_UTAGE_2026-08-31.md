# Utage English patch — handover, 2026-08-31

Sengoku BASARA 3 Utage (BLJM60389), in-battle dialogue. Game root:
`E:\Utage Patching New` (RPCS3 mounts it directly as `/dev_bdvd`).
Donor: Samurai Heroes at `E:\SAMURAI HEROES`.

Test case throughout: **m034 / pl015** (Mount Osore, Masamune). Second case: m019 / pl015.

---

## 1. State now

| | |
|---|---|
| Dialogue loading | **Fixed** (V15) |
| Mission banner overflow | **Fixed** (V16) |
| Dialogue box overflow | **Fix installed, untested** (V17) |
| Message-id drift vs Utage's script | **Open** |

Live counts in `rom/eng/id/` — 1410 mission message sets:

- **608** on the English route (606 from V15, plus m000/pl003 and m034/pl015 from V14)
- **802** untouched Japanese (Utage-only sets, no SH donor — leave alone)
- **0** broken

---

## 2. How the text system actually works

Three independent routes. Getting these confused cost several versions.

### Message route
`msg\%s\jpn\%s` — EBOOT string at file `0xe5d278`. The middle field is **hardcoded `jpn`**,
so a set's internal resource key stays `msg\m034_15\jpn\m034_15` even when the archive is
loaded out of `rom/eng/id/`. SH's route is `msg\%s\%s\%s` plus a hardcoded
`msg\ascii\eng\ascii`.

Utage's `EBOOT.BIN` is a **fake-signed SELF — plain ELF at file offset `0x980`**, fully
readable and patchable. `vaddr = file_offset - 0x980 + 0x10000`. TOC (r2) = `0x109b070`.

### Font route
**Utage has no global-font fallback.** A set with no local `.fnt` never resolves and
renders nothing. Every English set that works in Utage carries its *own copy* of the
global ASCII font under its own resource names. Verified byte-identical across
`id_pause`, `id_result`, `id_tenka`, Utage `msg\ascii\{jpn,eng}\ascii`, and SH's:

| resource | sha256 (first 16) |
|---|---|
| TNF | `df843e0b42390e89` |
| CSA | `9d5b493204cae29b` |
| page 00 | `bd9325a975d6b963` |
| page 01 | `2563fb5f4c3d54bc` |

### Layout route
`sBasaraLayout` prefix table (EBOOT `0xe5b9c0`–`0xe5ba50`), selected by `mLanguage`:

```
id\lsp\jpn    id\lsp\abr    id\lsp\com
id\mod\jpn    id\mod\com
id\texture\jpn   id\texture\kor   id\texture\twn   id\texture\eng
```

**`abr` and `texture\eng` are already in Utage's engine.** SH ships its HUD masters under
`abr` (identical across eng/fre/ger/ita/spa — it is the Western adaptation); Utage only
ever shipped `jpn`. Utage's cockpit has 241 nodes to SH's 172 — the extra 69 are Utage-only
HUD (tag system, 30Kumite, mission timer, roulette, Nyusin/Ninnuki counters), so the master
**cannot be swapped wholesale**; port node-by-node instead.

---

## 3. Resource formats

Loose-file extensions come from RPCS3 `sys_fs` fallbacks and identify each type. Load order
is the order below.

| ext | type hash | magic | contents |
|---|---|---|---|
| `.fnt` | `0x1D609FFB` | `\0TNF` | font — glyph rects |
| `.msg` | `0x10C460E6` | `\0GSM` | strings |
| `.mif` | `0x2EA515BF` | `\0FIM` | message metrics |
| `.tex` | `0x241F5DEB` | — | `_NN_ID_HQ` atlas pages |
| `.asc` | `0x5E0EF076` | `\0CSA` | char code → glyph index |

**TNF** — 32-byte header: magic, u32 0, u32 glyph_count, u32 cell_w, u32 cell_h, 12 zeros.
Then `glyph_count` × 8: `u16 glyph_id, u16 x, u16 y, u16 advance`. **`glyph_id >> 8` is the
atlas page**, so page count = `max(glyph_id) >> 8` + 1. ASCII font: 184 glyphs, cell 26×20,
2 pages. A mission's Japanese font: ~1008–1140 glyphs, cell 26×26, 13–14 pages.

**GSM** — 16-byte header: magic, u32 0, u32 unit_count, u32 record_count. Then
`record_count` × `(u32 offset, u32 length)`, then `unit_count` u16. **Each value is a TNF
record index, not a character code.** Decode by inverting the set's CSA. `chr(v + 33)` is
the ASCII shortcut and is only right above `&` (glyph 0 is space, 1–5 are `!"#$%`, `&` is
absent, 6 onward is `code - 33`).

Control codes (≥ `0xF000`, with inline operands): `0xFFFF` end · `0xFFFE` newline ·
`0xFFFD` page end · `0xFFFB`+1 · `0xFED2`+2 (speaker name id) · `0xFC16`+1 / `0xFC17`+3
(window open) · `0xFF92`+1 / `0xFF91` (colour span) · `0xFC12` · `0xFC0D`+1 · `0xFC0F`+1 ·
`0xFC11`. `0xD8xx` is a runtime substitution token (army/character name), so final width is
not known statically.

**FIM** — 32-byte header: magic, u32 0, u32 c1 (= GSM record_count), u32 c2, u32 c3, 12
zeros. Then c1 × 20-byte records and c2 × 44-byte records. Size is exactly
`32 + c1*20 + c2*44`; c3 is a subcount, not a size.
- 20-byte record `+14` u16 = **window style** (0 / 5 / 7 / 10 / 0xFFFE; style 7 is
  Utage-only); `+16` u32 = **message id**.
- 44-byte record `+0` u16 = **line count**, `+2` u16 = **character count**. SH writes 1–3.
  **Utage writes 1 in all 110,698 messages across every mission set** — its own dialogue
  never exceeds two lines.

**CSA** — 8-byte header (magic, u32 valid_count) then 128 u16: char code → TNF record index,
`0xFFFF` = absent. Mission tables are sparse (m019_15 has 13 entries); the ASCII table is
dense apart from `&`.

**LSP** (`0x60DD1B16`, magic `\0PSL`) — u16 @12 = node count, u16 @14 = animation-entry
count. Nodes are 176 bytes from offset 16:
`+0x00` pos (2 floats) · `+0x20` scale (3 floats) · `+0x30` flag · `+0x38` **node link** ·
`+0x48` size · `+0x70` flag · `+0x74` geo (4 int32 l,t,r,b) · `+0x84` uv (4 int32).
Texel = uv × 2 (`_ID_HQ` are 2× assets drawn at half scale).

After the node array comes a length-prefixed string table — `(u32 len, NUL-terminated
string)`, exactly **two strings per node (name, texture) in node order**, then one per
animation entry. Anchor the walk at `00 00 00 08 "SysRoot\0"`. **A regex scrape silently
drops one-character names like `0` and misaligns every index** — this produced a wrong
"the layouts are identical" conclusion once already.

Between the node array and the string table is the animation section: a flat sequence of
self-describing blocks, one per animation entry, walked in order. **No offset table
references them** (checked: no monotonic pointer field in the node records), so a block may
change length and everything after simply shifts. Track format: `u32 keycount`, then keys of
`{u32 frame, u32 interp, f32 value}`.

---

## 4. The three fixes

### V15 — mission-local ASCII font (dialogue was not loading at all)

**Cause.** V10/V11 stripped each set's local font (TNF + CSA + atlas) to match SH's shape,
assuming Utage would fall back to `msg\ascii`. It does not. RPCS3 log showed one failed
lookup for `/dev_bdvd/.../msg/m019_15/jpn/m019_15.fnt`, then a fallback load of set
`m000_00`, which has no archive — every resource ENOENT, zero dialogue.

**Fix.** Rebuilt all 606 stripped sets from the pristine Japanese archives:

```
TNF msg\<set>\jpn\<set>            = global ASCII TNF
GSM msg\<set>\jpn\<set>            = SH English text
FIM msg\<set>\jpn\<set>            = SH English metrics
XET msg\<set>\jpn\<set>_00_ID_HQ   = global ASCII atlas page 0
XET msg\<set>\jpn\<set>_01_ID_HQ   = global ASCII atlas page 1
CSA msg\<set>\jpn\<set>            = global ASCII char->glyph table
GSM/FIM  <set>_r                   = SH English
stage script + army name plates    = byte-identical Utage originals
```

Stale Japanese atlas pages 02+ dropped (the ASCII TNF never references a page above 1).
SH filenames reverse the fields: Utage `msg_m019_pl015.arc` ↔ SH `msg_pl015_m019.arc`.

### V16 — SH's `abr` message window and banner geometry

**Cause.** Utage only has the `jpn` HUD master; SH's `abr` master is re-proportioned for
Latin text.

**Fix.** Ported SH's `abr` values onto Utage's `jpn` master for the two message groups,
node-for-node by name — `3_0 3_0_0 Kao_L Kao_M Name Kamon 3_0_1 Mess1..4 Mask` and
`3_1 Line_U×2 Line_D×2 MesJ_M MesJ_L MesJ_R`:

- banner strip 34 → 44 units tall, rules ±15 → ±22, UV slice 57..91 → 33..95
- dialogue group drops 10 units; left cap and stretch shift 16 right; `Kamon` restored to a
  full 256×256 UV

**Copy only `pos` (+0x00), `geo` (+0x74) and `uv` (+0x84).** `+0x30` is the benign flag from
the V8 KOs finding; **`+0x38` is a node link** and copying it would point into a 172-node
tree from a 241-node one.

Result: **banner fixed, dialogue box unchanged** — its height is animation-driven.

### V17 — SH's three-line window state

**Cause.** The animation section's first three groups are the window's size states:
`Ani 0_0_0` / `0_0_1` / `0_0_2`, each over `Mess1 Mess3 Mess4 Name Kamon`. Utage and SH are
byte-identical through `Ani 0_0_1` and into `Ani 0_0_2`'s Mess1/Mess3 tracks, then diverge:
**SH's `Mess4` track is 448 bytes where Utage's is a 104-byte stub**, and SH keys scale on
`Name` where Utage has none. Capcom authored the three-line state for the West; Utage never
got it, so SH's third line fell out of the box.

**Fix.** Replaced Utage's whole `Ani 0_0_2` group with SH's, 2736 → 2784 bytes, in
`rom/{eng,jpn}/id/cockpit1P.arc`.

**`cockpit2P` deliberately skipped** — SH's 2p `Ani 0_0_2` is *smaller* than Utage's
(2632 vs 2736), so porting it would regress split-screen.

Block boundaries for reference (relative to the animation-area start, identical in both
games through entry 16):

```
14 Ani 0_0_2 7004..7796   15 Mess1 7796..8396   16 Mess3 8396..8700
17 Mess4  U 8700..8804  /  S 8700..9148
18 Name   U 8804..9272  /  S 9148..9568
19 Kamon  U 9272..9740  /  S 9568..9788
20 Ani 0_1_0 follows in both
```

---

## 5. Ruled out — do not re-investigate

- **Text rendering / font size.** Measured against the atlas: `M` ink is 22 texels → 11 px
  on screen, advance 17 → 17 px; letter-start deltas across "Masamune" are 17, 12, 12, 12
  against predicted 17, 13, 12, 13. Proportional, 1:1, correct.
- **Window texture.** SH `id\texture\eng\cockpit\cockpit_019_ID_HQ` is byte-identical to
  Utage's `jpn` copy (`b4eaccf4d91f`).
- **Node transforms.** Identical after V16; scale 1.0 on every window node in both games.
- **Control codes.** Utage's own record 500 and SH's are identical —
  `FC17 0000 0000 FFFF FFFB 000A FED2 0000 015D` — same box type, speaker, window style.
- **`msg\font`** (`0x6005E229`) is `\0LCF`, an 8-colour palette, identical in both games.
- **RPCS3 cache.** `dev_hdd1` caches only `battle/effect/enemy/player/stage`; every `id/`
  and `msg/` archive stats hdd1 (ENOENT) and falls through to bdvd. It is not shadowing
  patches.
- **Re-paginating SH's text.** SH does *not* split: 121 three-line and 9 four-line pages
  inside a single `FC17 … FFFD` block in m034_15, consistent across all five of its
  languages. Its window grows; don't rewrite the prose.
- **`title_id.arc` bloat.** The 31 `rom\eng\common\pl_face\plNNN` entries are 40-byte `SCRA`
  preload lists totalling **1,232 bytes**. Utage's file is 10 MB vs SH's 3.2 MB because it
  holds 116 `id` resources to SH's 71 (bigger roster). SH has no `rom\` entries, so they are
  non-standard, but they cost nothing.

---

## 6. Open threads

1. **Verify V17 in game** — m034/pl015, cold boot, no save state.
2. **Message-id drift.** SH's GSM/FIM go in wholesale, so ids drift against Utage's own
   script. m019_15: SH has 407 messages to Utage's 667; the id columns run parallel but
   diverge by one from about message 137. Utage-only lines have no SH source and stay blank.
   Fixing this means aligning the two id sequences and remapping SH's GSM into Utage's
   1966-slot table rather than replacing it.
3. **`mLanguage`.** Where it is set is not yet traced — the layout prefix pointers sit in a
   scattered literal pool at vaddr `0xffeb70`, too far from the TOC for a single `lwz`, so
   it needs the `lis`/`addis` pairs followed. Flipping the layout language to `abr` would
   let SH resources drop in under their native names instead of being renamed, and is the
   clean route if more `abr` assets turn out to be needed.
4. **`cockpit2P`** still has Utage's `Ani 0_0_2`; split-screen dialogue will still clip.
5. **The 802 Utage-only sets** remain Japanese — no SH donor exists.

---

## 7. Files

Tooling — `E:\Utage Patching New\_codex_tenka_v6\`:

| file | purpose |
|---|---|
| `arc_tools.py` | ARC v8 parse / unpack / rebuild-in-place |
| `arcbuild.py` | ARC rebuild **with entry removal** (V15 needs this) |
| `build_v15.py` | mission-local ASCII font, all 606 sets |
| `build_v16_layout.py` | SH `abr` node geometry port |
| `build_v17_anim.py` | SH `Ani 0_0_2` clip port |

Validation: `V15_REPORT.json` / `V15_LOCAL_ASCII_ALL_MISSIONS_VALIDATION.json`,
`V16_ABR_LAYOUT_VALIDATION.json`, `V17_ANI_0_0_2_VALIDATION.json`.

Backups (restore by unzipping over the game root):

- `V15_BACKUP_eng_id_pre_v15.zip` — 606 stripped msg archives, 49.6 MB
- `V16_BACKUP_cockpit_lsp_pre_v16.zip` — 4 cockpit archives, 2.0 MB
- `V17_BACKUP_cockpit1P_pre_v17.zip` — 2 cockpit1P archives, 1.0 MB

Distributable packages:

- `Utage_Battle_Dialogue_V15_LOCAL_ASCII_ALL_MISSIONS_ROOT_READY.zip` (64.0 MB)
- `Utage_Battle_Layout_V16_SH_ABR_MESSAGE_WINDOW_ROOT_READY.zip` (2.0 MB)
- `Utage_Battle_Layout_V17_SH_3LINE_WINDOW_STATE_ROOT_READY.zip` (1.0 MB)

Apply in order; V16 and V17 both touch `cockpit1P.arc`.

**Note:** close Kuriimu2 before installing — it holds an exclusive lock on any open `.arc`
and silently blocks the copy.
