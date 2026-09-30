# Cutscene / Subtitle Pipeline Recovery — 2026-09-30

This document preserves the current cutscene/subtitle engineering knowledge found in Drive canon so it is not trapped in private chat/Drive state.

## Keep three systems separate

### 1. Pre-rendered PAM movies
Path:
`PS3_GAME/USRDIR/nativePS3/movie/*.pam`

- MPEG-2 video
- ATRAC3plus audio
- subtitle strategy: replace/modify video GOP material while preserving original PAM container/interleave and original audio sectors
- full/remux replacement previously caused audio loss
- tested working direction preserved original audio sectors byte-for-byte

Referenced production tool:
`build_utage_pam_subtitle.py`

Referenced canon:
`PAM_PRODUCTION_CANON.md`

Referenced research root:
`E:\BASARA_RESEARCH\PAM_SUBTITLE_PIPELINE_2026-09-28\`

GitHub currently preserves:
- `project/media_tools/pamftool_utage_patch.py`
- `.github/workflows/build-utage-pamftool.yml`

### 2. Native in-engine cinematics
Families:
- `rom/demo/evs/*.arc`
- `rom/demo/evm/*.arc`
- `rom/demo/evp/*.arc`

These use MT Framework Lite's native caption path in LDS scene data.

Important class:
`uIdCaption`
class hash stored in LDS:
`0x0E286DCF`

Key properties:
- `mMsgId`
- `mMsgType`

Official Samurai Heroes bank mapping:
- type 0 -> caption
- type 1 -> caption_evs
- type 2 -> caption_evs2

Pristine Utage story EVS does not serialize mMsgType in the same way; the recovered writer grammar can insert/author the required property/curves.

### 3. Battle / mission dialogue
Primarily:
`rom/eng/id/msg_mNNN_plNNN.arc`

This is the GSM/FIM dialogue pipeline and must not be conflated with PAM or EVS/EVM cinematic captions.

## Recovered native LDS rules

- `mMsgId` descriptor uses a `0x060A00NN` tag family.
- low 16 bits = timed state/key count.
- frame keys stored as `frame << 8`.
- hidden state commonly `0xFFFFFFFF`.
- EVS localisation inserts a full 24-byte `mMsgType` descriptor where required.
- string/resource tokens and later pointers must be rebased carefully after insertion.
- typed descriptor-owned property data must not be blindly mistaken for table offsets.

The recovered writer was validated by byte-perfect regeneration against official SH samples, including 138/138 SH EVS inverse->forward round-trips according to the current Drive architecture checkpoint.

## Story EVS inventory

35 Utage EVS story cutscenes across eight protagonists:
- pl016 Muneshige — 2
- pl017 Hideaki — 2
- pl018 Yoshiaki — 5
- pl019 Tenkai — 5
- pl022 Sasuke — 6
- pl023 Kojuro — 8
- pl028 Hisahide — 6
- pl029 Sorin — 1

## Referenced local recovery scripts

Drive canon records these scripts under:
`E:\BASARA_RESEARCH\CUTSCENE_SUBTITLES_2026-09-28\tools\`

- `cutscene_caption_audit.py`
- `story_evs_audit.py`
- `extract_sh_caption_corpus.py`
- `reproduce_sh_evm000_00.py`
- `validate_evs_roundtrip_v2.py`
- `build_hisahide_native_evs_test.py`
- `parse_native_caption_lds.py`
- `install_yoshiaki_representative_gate.py`
- `promote_yoshiaki_after_gate.py`
- `rollback_yoshiaki_install.py`
- `promote_remaining_downstream_after_kojuro_gate.py`

## Durability warning

During this 2026-09-30 recovery audit, the filenames above were **not found as standalone source files in GitHub or Drive search**.

Therefore:
- architecture/algorithms/state are now backed up here;
- PAM tooling has partial GitHub preservation;
- the exact latest native-EVS authoring/install script bytes remain a local-only durability gap until E: access returns.

Do not claim those exact scripts are backed up when they are not.

## Drive canon provenance

Primary:
`00 SUBTITLE SYSTEM CROSS-CHAT CANON — 2026-09-28`
Drive id:
`1XFAbMKYyPVm970ODIVC3Vwkf1pFkZzYb3zwLiQhTHTU`

Additional architecture checkpoint:
`NATIVE_CUTSCENE_SUBTITLE_ARCHITECTURE_2026-09-28.md`
Drive id:
`102H0Xr06HTPgOqCRBTSLQZwyDPgNHmcD`

Late native state checkpoint:
`NATIVE_EVS_CURRENT_STATE_2026-09-28_2322.md`
Drive id:
`1TGJ5fsd2EkG5UOBlQIkE6CytKs2-TxV9`

The Drive canon remains useful evidence, but this GitHub note ensures the key architecture and missing-source inventory remain recoverable without relying on Drive.
