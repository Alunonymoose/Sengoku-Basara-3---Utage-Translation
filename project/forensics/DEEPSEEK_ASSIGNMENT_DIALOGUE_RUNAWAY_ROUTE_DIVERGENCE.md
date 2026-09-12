# DeepSeek Assignment — Dialogue Runaway / Runtime Route Divergence

## Objective
Find the root cause of the current universal in-stage dialogue runaway in the user's live local build, without modifying any game files until a causal mechanism is proven.

## Current hard evidence

### A. Current local runtime is `E:\Utage Patching New`
RPCS3 log boots:
`E:/Utage Patching New/PS3_GAME/USRDIR/EBOOT.BIN`

RPCS3 repeatedly reports executable fingerprint:
`PPU-e03e70a536e4e3693ebe5d6b729d6cc5fce411d1`

### B. Local runtime outer routes are JPN
The same current RPCS3 log opens from the disc tree:
- `nativePS3/rom/jpn/startup.arc`
- `nativePS3/rom/jpn/basara.arc`
- `nativePS3/rom/jpn/id/cockpit1P.arc`
- `nativePS3/rom/jpn/id/cockpit2P.arc`

There are no observed `nativePS3/rom/eng/id/...` opens in that log.

### C. This disagrees with the Drive UPN executable previously audited
Known Drive `UPN_EBOOT.elf`:
- size 17,440,144
- SHA-256 `a3cafcb5656a0d6ec7bdf9f2a273cb494e3e195950dd06b2c1d19ff97a43b99b`
- SHA-1 `d41878311602b1357e7828f002dff3fd94d81cf3`
- contains `rom\eng\startup`
- contains `rom\eng\basara`
- contains `rom\eng\msg`
- does not contain the corresponding literal `rom\jpn\startup`, `rom\jpn\basara`, `rom\jpn\msg` at those positions.

Known pristine stock Utage ELF:
- size 17,440,144
- SHA-256 `b1d23e53cbf33dd43ea04d6c57d4df651b0f3785496166c88b39ff68f89f69c9`
- SHA-1 `fd7d716cd3c0f00237573d0c995b000484e1ca4b`
- contains the JPN versions of those outer-route strings.

### D. Local runtime files also differ from the Drive snapshot
RPCS3 reports the local runtime `rom/jpn/id/cockpit1P.arc` size as:
`0x7ffda = 524,250 bytes`.

Drive UPN has:
- JPN `cockpit1P.arc`: 506,639 bytes
- ENG `cockpit1P.arc`: 488,447 bytes

So the local runtime tree is not simply the Drive snapshot with the wrong route; it has diverged at file-content level too.

### E. Current Drive dialogue sample itself looks structurally healthy
For Drive UPN `m034_pl013` and Utage-only `m045_pl013`:
- current Utage primary GSM slot counts match pristine Utage
- low-length/control slot index sets match pristine Utage
- FIM first section is exactly `32 + message_count*20` and is byte-identical to pristine Utage
- remaining FIM records are `44` bytes each; observed changes are confined to field 0 and are consistent with glyph/layout mapping
- current voice-side QRTS payloads match pristine Utage in sampled files
- `0xFFFE` additions are newline-format changes, not progression control corruption

Therefore do not re-propose the already-disproven claim that the current Drive sample is merely a reduced SH message table or that all blank slots were converted to dialogue.

## Input pack
Run `project/forensics/COLLECT_dialogue_runaway_forensics.ps1` from the repo on the user's machine. It is read-only and creates `UTAGE_DIALOGUE_FORENSICS_<timestamp>.zip` containing:
- local `EBOOT.BIN`
- JPN and ENG `startup.arc`, `basara.arc`, `cockpit1P.arc`, `cockpit2P.arc`
- JPN and ENG `id/msg_m034_pl013.arc`
- JPN and ENG `msg/m034_pl013.arc`
- JPN and ENG `id/msg_m045_pl013.arc`
- JPN and ENG `msg/m045_pl013.arc`
- dialogue inventory with SHA-256s
- newest RPCS3 log if found
- known reference fingerprints

## Required analysis

1. **Identify the exact local EBOOT lineage.**
   - Decrypt/extract executable payload if needed.
   - Hash it.
   - Compare route strings and relevant executable regions to stock Utage and known Drive UPN ELF.
   - Explain why current runtime selects `rom/jpn`.
   - Do not infer from filenames; prove from executable bytes and runtime log.

2. **Determine which mission dialogue namespace is actually live.**
   Trace or instrument runtime opens for one reproducible failing stage/player. Specifically determine whether the active text bundle is loaded from:
   - `rom/jpn/id/msg_mNNN_plNNN.arc`
   - `rom/eng/id/msg_mNNN_plNNN.arc`
   - cache under `/dev_hdd1/...`
   - another dynamically constructed path.
   Do the same for the `rom/.../msg/mNNN_plNNN.arc` companion.

3. **Compare the exact locally-live mission pair, not Drive substitutes.**
   For the live JPN/ENG candidate pair:
   - ARC entry count/order/types/flags
   - GSM count and table `(offset,length)` values
   - per-index control tokens
   - FIM header counts
   - full 20-byte message-map section
   - 44-byte format records field-by-field
   - `_r` resources
   - QRTS or equivalent voice reference resource
   - any STQ / event / queue-index resources referenced by that archive

4. **Find the progression/queue consumer.**
   The user symptom is: at some point in every stage dialogue starts playing continuously until it runs out.
   Trace the code or data field that advances/selects the next dialogue event. The answer must identify at least one of:
   - event queue/index cursor
   - sentinel/end condition
   - trigger flag
   - event-to-message index mapping
   - STQ/event timing table
   - callback/state transition
   - provider/index mismatch that makes the consumer believe every subsequent row is ready

5. **Produce a causal A/B patch design only after proof.**
   The smallest diagnostic should change exactly one proven causal layer. It must preserve English glyph payload wherever possible and have a rollback.

## Evidence labels
Use only:
- PROVEN
- STRONGLY SUPPORTED
- OPEN
- DISPROVEN

Do not call a theory a fix.

## What ChatGPT needs returned
Return one Markdown report containing:

### 1. Local executable identity
- SHA-256
- route strings / offsets
- whether it is stock, UPN-derived, or another branch
- why RPCS3 is opening `rom/jpn`

### 2. Actual live dialogue files
For one reproduced failing stage/player, list the exact files opened and their SHA-256s.

### 3. First causal divergence
Give the earliest structurally meaningful difference between a known-good Utage flow and the failing local flow. Include offsets/record indices and decoded field meaning if known.

### 4. Consumer mechanism
Show the code/data path that turns that divergence into runaway playback.

### 5. Minimal diagnostic fix
Specify exact bytes/resources/files to alter, expected behavior, and rollback.

### 6. Unknowns
Explicitly list anything not proven.

Do not spend time on Gallery, caption_evs, UI textures, or general translation completeness unless they directly enter the stage-dialogue runtime call path.
