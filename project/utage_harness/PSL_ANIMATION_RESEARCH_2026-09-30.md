# PSL animation / runtime reconstruction checkpoint — 2026-09-30

Status: **research-supported; parser integration still in progress**.

This note records findings from read-only tests against the current live Utage ENG tree and RPCS3 RRC captures. No live game bytes were changed.

## Confirmed PSL v0x21 structure

For the tested SB3/Utage `\0PSL` resources:

1. 16-byte big-endian header.
2. `node_count` fixed 176-byte node records.
3. animation/control table beginning immediately at `16 + node_count*176`.
4. node name table, located by the counted `SysRoot\0` string.
5. exactly two unaligned counted strings per node: node name + texture name (texture may be empty).
6. after node strings, one counted name per animation/control record when that variant is decoded exactly.

Title `title.lsp` currently has 136 nodes and 153 animation/control records.

## Node fields supported by live evidence

- `0x00,0x04`: local X/Y position.
- `0x18`: 2D Z rotation in degrees.
  - live examples: -21, 144, 176 degrees.
  - animation rotation track values use the third float and match this convention.
- `0x20,0x24`: local X/Y scale.
- `0x38`: parent node index.
- `0x40`: generic link field; when it targets a type-5 node it consistently behaves as a mask/clip link on title assets.
- `0x48,0x4C`: source texture dimensions / size metadata.
- `0x54`: node type.
- `0x60`: material index.
- `0x74..0x80`: local geometry rectangle.
- `0x84..0x90`: logical UV rectangle.
- physical XET crop = logical UV * 2 for the proven Utage UI path.
- `0x94..0xA0`: four packed color values. High byte tracks opacity consistently enough for the title animation renderer; RGB semantics remain material/shader dependent.

## Animation table correction

An earlier candidate decoder treated several control words as 2-word keyed tracks. That silently worked while those words were zero, then desynchronized on enabled channels.

The strongly supported structure alternates control/scalar words with keyed tracks:

- channel 0: scalar/control
- channel 1: position keys, 6 words/key
- channel 2: scalar/control
- channel 3: rotation keys, 6 words/key
- channel 4: scalar/control
- channel 5: scale keys, 6 words/key
- channel 6: scalar/control
- channel 7: unknown keyed track, 2 words/key
- channel 8: scalar/control
- channel 9: UV-rect keys, 6 words/key
- channel 10: scalar/control
- channel 11: color 0 keys, 3 words/key
- channel 12: scalar/control
- channel 13: color 1 keys, 3 words/key
- channel 14: scalar/control
- channel 15: color 2 keys, 3 words/key
- channel 16: scalar/control
- channel 17: color 3 keys, 3 words/key
- later channel pairs remain under investigation.

With this correction, animation-table parsing ended **exactly at the node-name table** for 12 of 15 tested live layouts:

- title/title
- title/mode_select
- title/tenka_makura01
- title/common_00
- com/fade
- result_id/title/kakusyu
- result_id/common_00
- result_id/tenka/top_00
- result_id/result/result_00
- result_id/tenka_makura01
- versus/kessen_rule
- versus/kessen_sele

Remaining divergent layouts at this checkpoint:

- title/color
- result_id/tenka/soubi_00
- quest/yuugi_quest

Those should be treated as additional animation-record variants, not forced through the title schema.

## Title animation evidence

The current title animation table parses all 153 records exactly.

Root records include:

- `logo_scale ----------------------`
- `logo_fadeout --------------------`
- `logo_skip -----------------------`
- `Aspect_4:3`

Examples:

- `logo_sengoku`: scale + color track, duration 23.
- `logo_basara`: scale + color track, duration 31.
- `logo_3`: color track, duration 72.
- `logo_shadow_00/01`: color tracks, duration 159.
- logo flash nodes carry color tracks under the main root.
- interpolation codes observed in exact layouts: 3 overwhelmingly common, 0 and 5 less common.
  - code 3 is consistent with ordinary interpolated motion/color.
  - code 0 behaves like hold/step in current prototype.
  - code 5 is currently approximated as eased interpolation and still needs runtime proof.

## Mask evidence

When node field `0x40` points to a type-5 node on title assets, the target names and use are strongly mask-like:

- `moyou_01 -> moyou_01_mask`
- `moyou_02 -> moyou_02_mask`
- `moyou_03 -> moyou_03_mask`
- `line_small_* -> line_small_mask`
- `chara_* -> chara_mask`
- `logo_3_effect_00 -> logo_3_mask_00`
- `logo_3_effect_01 -> logo_3_mask_01`
- `Wind -> Wind_mask`

Some type-5 masks use a large real alpha texture. Others sample a tiny solid-white area and rely mainly on the mask node geometry. Therefore the reconstruction should rasterize the linked mask node in screen space and multiply the source layer alpha, not merely crop by texture alpha.

Do not globally rename field 0x40 to “mask”; other layouts contain non-type-5 targets. Use “link_40”, with mask semantics only when the target is proven type 5.

## Node-type evidence

Do **not** render every node that has a texture string as a normal sprite.

A prototype that rendered type 2/3/4 texture-bearing nodes as ordinary quads produced large incorrect white slabs. Restricting ordinary sprite rendering to type 2 restored a coherent title composition. Type 3/4 rendering semantics remain separate work.

## Affine renderer prototype

An isolated, non-canonical prototype was tested with:

- hierarchical parent transforms
- static + animated Z rotation
- scale and position interpolation
- UV animation
- packed-alpha animation
- type-2 draw eligibility
- linked type-5 masks
- logical 640x480 -> output surface mapping

Frames 25, 50, 88 and 132 of the title sequence reconstruct coherently from live ARC/XET/PSL bytes. The remaining obvious differences are primarily unsupported type-3 semantics/material effects and exact interpolation/blend behaviour.

## RRC v6 findings

The candidate RRC parser successfully decoded serialized RSX register state from a real capture.

Observed render passes in one capture included:

- 640x360
- 320x180
- 1280x720
- final 720x480

The final 720x480 state used:

- viewport offset: 360, 240, 0.5, 0
- viewport scale: 360, -240, 0.5, 0

This proves a capture may contain multiple render-target/viewport passes. Do not treat the final viewport as proof that every draw in the capture used that size.

The title PSL has an explicit `Aspect_4:3` animation/control name and a 320,240 root-centering pattern, supporting a 640x480 logical UI coordinate system. The harness may map that logical surface into the active RSX output surface, but must preserve the distinction between logical UI coordinates and physical render-target dimensions.

## Integration rule

Do not overwrite the current local uncommitted animation-decoder work in the GPT worktree. Merge only after:

1. identifying the owner/intent of those local edits;
2. correcting scalar-vs-track channel structure;
3. preserving the exact-parsing cases above;
4. keeping divergent animation variants fail-closed rather than guessing;
5. validating affine/mask rendering against runtime screenshots/RRC where possible.



## 2026-09-30 follow-up: full animation-schema regression

A corrected channel-width search was run against all currently targeted live layouts.

The shared exact-end schema is:

- channel 7: **6 words/key**, not 2;
- channel 21: **3 words/key**, not 2;
- channel 19: provisionally 2 words/key, but it was zero in all 16 regression layouts and therefore remains unproven.

With channel 7 = 6 and channel 21 = 3, **16/16 tested live PSL animation/control tables land exactly on the SysRoot name-table boundary**:

- title/title
- title/color
- title/mode_select
- title/tenka_makura01
- title/common_00
- title/com/fade
- result_id/title/kakusyu
- result_id/common_00
- result_id/tenka/top_00
- result_id/tenka/soubi_00
- result_id/result/result_00
- result_id/tenka_makura01
- result_id/com/fade
- quest/yuugi_quest
- versus/kessen_rule
- versus/kessen_sele

This supersedes the earlier “12 of 15” status above.

### Channel 7 identification

Channel 7 is an **animated geometry rectangle**:

- key layout = time, interpolation, x0, y0, x1, y1;
- rectangle values are signed integers.

Examples:

- title/color: `(-430,-287,430,0)`
- soubi_00: `(0,-59,260,59)` → `(0,-59,344,59)` → `(0,-59,385,59)` → `(0,-59,398,59)`

These are not floating-point values.

### Channel 21 identification

Channel 21 is a **visibility / enable toggle**:

- key layout = time, interpolation, value;
- observed interpolation is 0;
- observed values are 0/1.

Examples:

- soubi_00 node `Suji`: frame 0 = 0, frame 23 = 1, frame 30 = 0
- yuugi_quest node `Q_K`: frame 0 = 0, frame 18 = 1, frame 22 = 0
- yuugi_quest node `Down_K`: frame 0 = 0, frame 15 = 1, frame 22 = 0

## Node type 3: vertex-coloured textured quad

Type-3 nodes should not be rendered as plain unmodulated texture quads.

Across title/mode_select/common/versus layouts, type-3 nodes overwhelmingly carry four distinct packed colours at 0x94/0x98/0x9C/0xA0.

Strong ordering evidence is **TL, TR, BL, BR**. Example `tenka_makura/shinki01`:

- TL = white
- TR = gray
- BL = white
- BR = gray

This exactly describes a left-to-right fade.

Packed colour is strongly consistent with AARRGGBB for type-3 vertex modulation. A prototype using bilinear four-corner A/R/G/B modulation turned previously incorrect white slabs into deliberate blue/cyan gradient UI layers.

Important material distinction:

- type 3: full four-corner RGBA vertex modulation is strongly supported;
- type 2: applying RGB modulation globally is wrong for the title materials. Type-2 values such as `FF000000` do not mean “multiply the sprite black” in those materials; alpha/control behavior is more plausible. The prototype therefore preserves type-2 texture RGB and uses packed alpha separately.

This is material-sensitive and should stay fail-closed where the material mapping is unknown.


## 2026-09-30 follow-up: direct Utage EBOOT runtime-class evidence

A read-only string/structure probe of the current Utage EBOOT found the game’s own layout runtime class names.

### Resource and unit classes

At the rLayoutSpr reflection/string area:

- `mLayoutSpr`
- `rLayoutSpr`

At the uLayoutSpr area:

- `mPause`
- `mStop`
- `mFrame`
- `mSpeed`
- `mpResource`
- `resource`
- `mLayoutSpr`
- `uLayoutSpr`

This directly supports the harness model of a layout resource plus runtime frame/speed playback state.

### cLayoutSprite runtime fields

The EBOOT contains a reflected/runtime `cLayoutSprite` class with these nearby field names in declaration/reflection order:

- `mID`
- `mIsActive`
- `mIsUpdate`
- `mInheritance`
- `mParentRelate`
- `mType`
- `mCenter`
- `mIsDisp`
- `mIsShake`
- `mPos`
- `mRot`
- `mScale`
- `mSprRect`
- `mImageRect`
- `mColor0`
- `mColor1`
- `mColor2`
- `mColor3`
- `mBlendState`
- `mShaderType`
- `mprTexture`
- `resource`
- `mPass`
- `mMaskID`
- `mIsMaskEx`
- `mpMaskSpr`
- `mFreeUse`
- `mIsLocalize`
- `mPri`
- `mWPri`
- `mSubPri`
- `mTexSize`
- `mTexSizeWii`
- `mTexPath`

The same area also names the animation-side fields:

- `mAnimPos`
- `mAnimRot`
- `mAnimScale`
- `mAnimSprRect`
- `mAnimImageRect`
- `mAnimColor0..3`
- `mAnimSprDisp`
- `mAnimSprShake`

These names directly validate the decoded position/rotation/scale/geometry/UV/color/visibility channels. In particular, channel 7 corresponds to `mAnimSprRect`, channel 9 to `mAnimImageRect`, and channel 21’s visibility behavior matches `mAnimSprDisp`.

### Serialized node field naming

Combining runtime names with the serialized value domains gives strong field identifications:

- serialized `0x60` = **mShaderType** (large family selector; values observed well beyond the small blend enum range);
- serialized `0x68` = **mBlendState** (small selector; observed 0/1/2/5 and strongly correlated with render behavior).

This supersedes the earlier provisional labels “material” for 0x60 and “candidate blend/sampler” for 0x68.

Other integer/control fields should remain generically named until their exact serialized mapping is proven.

### EBOOT shader/blend infrastructure

The same EBOOT contains the engine shader package parser strings and enum vocabulary:

- `BlendEnable`
- `SrcBlend`
- `DestBlend`
- `BlendOp`
- alpha equivalents
- `BLEND_ZERO`, `BLEND_ONE`, `BLEND_SRC_ALPHA`, `BLEND_INV_SRC_ALPHA`, etc.
- `nDraw::BlendState`
- `nDraw::SamplerState`

This confirms that exact blend equations are represented explicitly in the engine. Mapping cLayoutSprite mBlendState enum values to those equations remains the next step.


## 2026-09-30 follow-up: sprite IDs vs node indexes

A later regression exposed an important distinction in serialized PSL references.

### Node ID field

Serialized node field 0x50 is the sprite/node ID used by animation targeting and
some generic links. This ID is not guaranteed to equal the node's array index.

Across the 16 regression layouts used above:

- 888 animation/control records have a non-negative target value.
- 886/888 resolve to exactly one node by serialized 0x50 ID.
- only 136/888 happen to name-match when the raw target is treated as an array index.
- the two unresolved targets are both tenka/top_00 records targeting raw ID 102
  (8_0 and 4_0), suggesting one exceptional/virtual target rather than index semantics.

Example from mode_select:

- animation record STORY_effect has raw target 95;
- node index 100 is named STORY_effect;
- node index 100 has serialized node ID 95.

Therefore animation records must resolve target values through node ID, not direct
array indexing. The harness now exposes the raw value as target_id and resolves it
through Layout.node_by_id().

### Parent hierarchy stays index-based

This rule does not apply to serialized parent field 0x38.

Example from mode_select:

- node index 100 STORY_effect has parent raw value 18;
- node array index 18 is the actual STORY parent;
- sprite ID 18 resolves to a different node.

Therefore parent hierarchy traversal remains array-index based.

### link_40 is ID-based

link_40 also resolves through serialized node ID rather than array index.

Strong examples:

- mode_select/top_00: raw link 55.
  - array index 55 = ordinary line_L_top_03 type-3 sprite;
  - sprite ID 55 = node index 16 MASK_00, type 5.
- result_00/Base node 223: raw link 598.
  - 598 is outside the node-array range;
  - sprite ID 598 = node index 591 Mask, type 5.
- soubi_00/Wep_K: raw link 467.
  - array index 467 is an unrelated type-2 sprite;
  - sprite ID 467 = node index 65 mask, type 5.

Across the tested layouts, 41/47 non-negative link_40 values resolve to a type-5 node
by ID, versus 33/47 if misread as an array index. The remaining six ID targets are
non-type-5 generic relationships, so link_40 should remain generically named and
only receive mask semantics when its ID target is proven type 5.

### Clip/container selection

Animation records form both simultaneous subtrees and folders of alternative clips.

Examples:

- fade/Ani 0 contains alternative Ani 0_0 (fade out) and Ani 0_1 (fade in).
- title/color/Ani 1 contains six alternative mode-colour clips.
- the same root-folder -> child-clip pattern appears in common, equipment, result,
  quest and versus layouts.

The renderer therefore accepts any animation record as a selection. A targetless
record with multiple targetless direct children is treated as a clip container and
fails closed until one child clip is selected, rather than evaluating all alternatives
at once.

### Runtime blend-state caution

RRC capture BLJM60389_20260925092042_capture.rrc.gz provided several unique
texture-owner correlations:

- logo_kamon (shader 6, mBlendState=1) -> blend disabled, ONE/ZERO, alpha test on.
- logo_shadow_01 (shader 5, mBlendState=0) -> SRC_ALPHA / ONE_MINUS_SRC_ALPHA.
- Utage (shader 1, mBlendState=5) -> SRC_ALPHA / ONE_MINUS_SRC_ALPHA.
- Wind (shader 2, mBlendState=0) -> SRC_ALPHA / ONE_MINUS_SRC_ALPHA.

Therefore mBlendState alone must not be treated as a one-to-one RSX blend-equation
selector. Effective GPU state is at least shader/material-path dependent.


### Full live ENG ID/link sweep

The ID/index findings were then checked across the complete live ENG tree:

- 4,075/4,075 ARCs parsed.
- 87 PSL layouts.
- 14,859 nodes.
- 7,954 animation/control records.
- 5,871 records have a non-negative target.
- 5,863 target IDs resolve uniquely.
- 4 target IDs exist but are duplicated inside their layout.
- 4 target IDs are missing; all are the same top_00 raw ID 102 case duplicated across two owning ARCs.
- only 453 target-bearing records name-match when the raw target is incorrectly treated as an array index.
- 4,046 target-bearing records name-match directly through serialized node ID; many other valid animations target helper/group nodes whose names intentionally differ.
- all 14,772 non-root parent values are valid node-array indexes, confirming parent hierarchy remains index-based.

For link_40 across the same full tree:

- 202 non-negative links.
- 202/202 resolve to exactly one serialized node ID.
- 175 resolve to type-5 mask nodes.
- only 41 would land on a type-5 node if misread as an array index.

Six layouts contain at least one duplicate node ID. Four animation records currently target one of those duplicate IDs and cannot be disambiguated from serialization alone. The harness therefore fails closed for ambiguous animation targets rather than guessing. Proven type-5 mask links are unaffected: every live link_40 ID is unique in this sweep.

Machine-readable report:
E:\BASARA_WORK\jobs\utage_harness_anim\FULL_ENG_ID_LINK_SWEEP_2026-09-30.json


## 2026-09-30 follow-up: direct rLayoutSpr 0xB0 node deserializer proof

The Utage EBOOT's `rLayoutSpr` callback table resolves to LSP-specific load/save code around `0x1426E4` and `0x143ED0`.

The loader uses an explicit `0xB0` byte node-record size at `0x1429AC`, `0x142A14`, and `0x142A28`: it zeros a `0xB0` temporary record, reads exactly `0xB0` bytes from the resource stream, then expands that record into a `cLayoutSprite` runtime object. The save path uses the same `0xB0` size at `0x143FEC`, `0x14401C`, and `0x14416C` and performs the inverse mapping. This independently proves the 176-byte fixed node record used by the parser.

### Direct serialized -> runtime mapping

The deserializer establishes these mappings without inference:

| PSL node offset | cLayoutSprite runtime destination | Supported meaning |
| --- | --- | --- |
| `0x00..0x0F` | current `+0x90..0x9F` | `mPos` |
| `0x10..0x1F` | current `+0xA0..0xAF` | `mRot` |
| `0x20..0x2F` | current `+0xB0..0xBF` | `mScale` |
| `0x30` | current byte `+0xF4` | `mIsDisp` |
| `0x34` | current byte `+0xF5` | `mIsShake` |
| `0x38` | `+0x114`, later resolved to pointer `+0x100` | parent node reference |
| `0x3C` | boolean byte `+0x0C` | runtime control flag; exact public field name not promoted |
| `0x40` | `+0x1FC`, later resolved to pointer `+0x110` | ID-based generic link; type-5 targets are masks |
| `0x44` | signed byte `+0xF7` | control field; exact public name not promoted |
| `0x48` | `+0x1F4` | texture-size metadata |
| `0x4C` | `+0x1F8` | texture-size metadata |
| `0x50` | `+0x04` | `mID` |
| `0x54` | `+0x10` | `mType` |
| `0x58` | `+0x14` | centre/control field; exact public name not promoted |
| `0x5C` | `+0x18` | `mPass` |
| `0x60` | `+0x1C` | `mShaderType` |
| `0x64` | boolean byte `+0xF6` | mask-related control; exact public name not promoted |
| `0x68` | `+0x20` | `mBlendState` |
| `0x6C` | `+0x24` | control field; exact public name not promoted |
| `0x70` | boolean byte `+0x1EB` | control flag; exact public name not promoted |
| `0x74..0x80` | current `+0xC0..0xCC` | `mSprRect` |
| `0x84..0x90` | current `+0xD0..0xDC` | `mImageRect` |
| `0x94..0xA0` | current `+0xE0/+0xE4/+0xE8/+0xEC` | `mColor0..mColor3` |

The final `0xA4/0xA8/0xAC` words are not consumed by this expansion path and remain reserved/unknown rather than receiving invented semantics.

### Base/current runtime state

Reflection accessors expose separate base and current/animated state:

- `mIsDisp`: base byte `+0x09`, current byte `+0xF4`.
- `mIsShake`: base byte `+0x0E`, current byte `+0xF5`.
- `mPos`: base `+0x60`, current `+0x90`.
- `mRot`: base `+0x70`, current `+0xA0`.
- `mScale`: base `+0x80`, current `+0xB0`.
- `mSprRect`: base `+0x30`, current `+0xC0`.
- `mImageRect`: base `+0x40`, current `+0xD0`.
- `mColor0..3`: base `+0x50/+0x54/+0x58/+0x5C`, current `+0xE0/+0xE4/+0xE8/+0xEC`.
- `mPass` getter/setter uses runtime `+0x18`.

Immediately after each `0xB0` record is expanded, helper `0x83EDA0` copies those current values into their corresponding base fields, including current `mIsDisp -> +0x09` and current `mIsShake -> +0x0E`.

This gives an end-to-end engine-backed path:

`serialized node record -> current cLayoutSprite state -> base cLayoutSprite state`.

### Renderer consequence

Static layout reconstruction can now honor serialized node `+0x30` as default display without name heuristics or alpha guesses.

For an explicit animation preview, the harness activates the selected animation target before applying its channels because legitimate effect sprites can be hidden at rest and externally activated when their clip plays. An explicit `mAnimSprDisp`/visibility key remains authoritative.

Regression after integrating default display:

- 4,075/4,075 live ENG ARCs parsed.
- 87/87 PSL layouts parsed.
- 14,859 nodes.
- 7,954 animation/control records.
- zero ARC or layout failures.
- mode-select static reconstruction: 63 rendered, 22 hidden/skipped.
- selected `STORY_effect`: node 100 renders even though its resting `mIsDisp` is false.
- title `logo_scale` frame 96 remains coherent.
