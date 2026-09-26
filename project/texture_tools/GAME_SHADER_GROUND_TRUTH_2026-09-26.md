# Game shader ground truth: 0x2A YCbCr constants in Capcom's rShaderPackage (2026-09-26)

**Status: CONFIRMED IN GAME CODE.** The game's own compiled pixel shaders
decode 0x2A textures with neutral chroma 123. That is the constant the
project's codec has used since the Kuriimu2 port. Before this, the evidence
was a third-party tool (Kuriimu2) plus two runtime fixtures. It now also comes
from the game binary itself.

Source: the user's `sa.zip` (2026-09-26), taken from the Utage install root
`PS3_GAME/USRDIR/nativePS3/{sa,sc,system}`. It holds no localisable text.
No game bytes are committed. Only hashes, offsets and constants appear here.

## 1. The finding

`nativePS3/sc/PS3/Basara/package.spkg` and `nativePS3/sc/PS3/package.spkg`
are MT Framework `rShaderPackage` resources: magic `\0KPS`, type hash
`0x02358E1A`. They hold the compiled RSX programs. The RSX stores
fragment-program constants as big-endian IEEE floats with the two 16-bit
halves swapped. Read that way, the packages contain the BT.601 YCbCr→RGB
matrix, each time with a chroma offset of **−123/255**:

| Constant | Stored bytes (RSX order) | Value | Role |
|---|---|---|---|
| chroma offset | `f6f9bef6` | −0.482353 (= −123/255 to 6 places) | `Cb' = Cb − 123`, `Cr' = Cr − 123` |
| r_cr | `74bc3fb3` | 1.402 | `R = Y + 1.402·Cr'` |
| g_cb | `331e3eb0` | 0.34414 | `G = Y − 0.34414·Cb' − 0.71414·Cr'` |
| g_cr | `d1e13f36` | 0.71414 | ″ |
| b_cb | `d0e53fe2` | 1.772 | `B = Y + 1.772·Cb'` |

Counts (from `find_shader_ycbcr_constants.py`; see §3):

| File | Size | sha256 (first 16) | Complete sets, offset −123/255 | Sets, −128/255 or −0.5 |
|---|---|---|---|---|
| `sc/PS3/Basara/package.spkg` | 15,725,320 | `5e16c7063535bae0` | **16** | 0 |
| `sc/PS3/package.spkg` | 27,796 | `0e3c036d20a674dc` | **1** | 0 |
| `sc/PS3/Basara/Game/package.spkg` | 180,744 | `56e5ff0abc9c3c2d` | 0 | 0 |
| `sa/PS3/**/package.arc` | — | — | ARC wrappers: each holds one `\0KPS` member identical to the `sc` file above | — |

A "set" means all five constants within 512 bytes of each other. In practice
each of the 16 sets spans ≤ 164 bytes: one program's constant block. All 16
sit between `0xE09CB8` and `0xEFECA8` in the main package. **No textbook
offset (−128/255 or −0.5) occurs in any decode set anywhere in the dump.**

## 2. What this settles, and what it does not

**Settled:**
- The neutral chroma is **123**, not 128. `basara.xet.NEUTRAL_CHROMA = 123` is the game's own value.
- `basara.xet` decode agrees with the game's float math to well under one
  8-bit level across the full storage cube. This is tested in
  `project/basara/tests/test_text.py::test_ycbcr_constants_match_capcom_shader`.
- Decode coefficients: the game uses 0.34414 / 0.71414. Older notes used
  0.344136 / 0.714136. The difference is < 0.1 level, so both describe the
  same shader.
- The 0x2A evidence level is now **code-confirmed + runtime-proven**:
  - game shader (this doc);
  - title_004 (2026-09-18);
  - menu.arc member 58 (2026-09-25).

  Any future claim that 0x2A is "plain BC3", "needs an endpoint swap" or
  "uses 128" contradicts the game binary and fails closed.

**Not settled:**
- *Which* shader programs these are (material, UI or primitive). The SPKG has
  no names. The names live in `system/shader/ShaderPackage.mfx` (`\0XFM`),
  which shares the build stamp `0x32F8D5F6` with the package. Mapping program
  index → technique name has not been done. It is not needed for production.
- 0x2B (YCbCr + RBxG base/mask) is untouched by this finding. It stays
  read-preview only.
- The encode direction (RGB → YCbCr) is not in the shader, because the game
  only decodes. The writer's forward matrix (`Y=.299R+.587G+.114B`,
  `Cb=123−.168736R−.331264G+.5B`, `Cr=123+.5R−.418688G−.081312B`) is the exact
  inverse of the confirmed decode. Its runtime proof is still title_004 and
  menu.arc 58.

Supporting, not load-bearing: the MFX symbol table names a texture-cache path
`FSystemCacheCopyY`, `FSystemCacheCopyCb`, `FSystemCacheCopyCr`,
`FSystemCacheDecodeCopy`. It also contains an FMV decoder
(`FYUVDecoder`, `tYUVDecoderY/U/V`) and a TV-noise filter (`rgb2yuv`/`yuv2rgb`).
The FMV YUV path is separate from the 0x2A texture path.

## 3. Reproduce it

Read-only, standard library only:

```bat
python project\texture_tools\find_shader_ycbcr_constants.py "E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3"
```

Expected: `TOTAL rsx sets in plain files: -123/255 = 17, -128/255 = 0, -0.5 = 0`
and `VERDICT: CONFIRMS neutral chroma 123`. The tool reports −128/255 and −0.5
sets separately, so it can falsify the rule as easily as confirm it.

## 4. Other native-root facts identified from the same dump

| Resource | What it is | Consequence |
|---|---|---|
| `system/font/Gothic_AM_NOMIP.tex` (sha256 `1106b8d0…`) | XET 0x19 (BC1), 1024×512, 1 mip. Japanese **system** font, glyphs in JIS X 0208 row order | Not the dialogue/UI font: that is the per-archive TNF/CSA pair handled by `basara.font`. Which screens, if any, use it has not been established |
| `system/texture/sysfont_AM_NOMIP.tex` (`87ef8fe5…`) | XET 0x19, 1024×16. ASCII debug font strip | Debug only |
| `system/texture/DefaultCube_CM.tex` (`8e562b6b…`) | Cube map: header +0x0C low byte = **6 images**, format 0x23, lighting floats before the mip offsets | `basara.xet.xet_info` now **refuses** multi-image XETs with a clear reason instead of misreading them (`test_cube_map_xet_is_refused_with_a_clear_reason`) |
| `system/shaderRev.arc` (`82649c60…`) | 17 `\0VET` members (type `0x468C2F93`) named `system\shader_wii\tXf*` | Wii-build leftovers. Not relevant to localisation |
| `system/shader/ShaderPackage.mfx` (`3abf7060…`) | `\0XFM` effect/symbol table for the packages (techniques, samplers, constant buffers) | The names source if program mapping is ever needed |

## 5. Where this is recorded

- Canon: `TEXTURE_PIPELINE_CANON_2026-09-25.md` §3 (evidence chain) and §7 (evidence levels).
- Code: the `basara.xet` module docstring; `xet_info` image-count guard.
- Tests: `project/basara/tests/test_text.py` (2 tests).
- Skills: `.claude/skills/basara-texture-engineering/SKILL.md`, `project/skills_updates_2026-09-25/utage-texture-pipeline/SKILL.md`.
- Drive: `00 GAME SHADER GROUND TRUTH — 0x2A YCbCr CONSTANTS FROM rShaderPackage — 2026-09-26` (canon folder).
