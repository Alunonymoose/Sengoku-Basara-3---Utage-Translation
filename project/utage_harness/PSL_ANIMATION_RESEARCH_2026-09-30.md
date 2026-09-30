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

## 2026-09-30 cross-game confirmation: channel 19 width

Samurai Heroes `title_id.arc` exposed the first tested nonzero channel-19 tracks.

Layout:
- `id\lsp\abr\chara_select\chara_select`
- PSL v0x21
- 111 nodes
- 68 animation records

With channel 19 treated as 2 words/key, parsing desynchronized after the first nonzero track and eventually failed on a false `0xFFFFFFFF` UV key count.

Changing channel 19 to **3 words/key** makes the whole archive parse exactly:
- 6/6 SH title_id layouts clean;
- 262/262 animation records parsed;
- zero unresolved animation targets;
- zero duplicate sprite IDs.

The same change leaves all tested Utage layouts unchanged and clean.

Therefore the shared v0x21 schema is now:
- channel 19: **3 words/key** (confirmed cross-game, superseding the earlier provisional 2-word assumption).

## 2026-09-30 correction: channels 19 and 21 semantics

Cross-game key data identifies the final two keyed channels:

- channel 19 = **mAnimSprDisp / visibility**
- channel 21 = **mAnimSprShake / shake enable**

Evidence:
- Samurai Heroes `chara_select/l_obi_null00` channel 19 keys:
  - frame 0 = 1
  - frame 40 = 0
  - frame 160 = 0
- Utage `yuugi_quest/Ghb_kakutoku` channel 21 keys:
  - frame 0 = 0
  - frame 15 = 1
  - frame 22 = 0

This supersedes the earlier provisional statement that channel 21 was visibility.

The offline renderer now:
- applies channel 19 to node visibility;
- preserves channel 21 as an explicit `shake` state;
- does not invent shake displacement until runtime amplitude/phase semantics are decoded.

### Step-key timing correction

Interpolation code 0 is a hold/step mode, but an exact key timestamp must select the new key immediately.

The sampler previously returned the left key when `frame == next_key.time`, making discrete visibility/shake changes one frame late.

Correct behavior now:
- SH visibility becomes 0 exactly at frame 40;
- Utage shake becomes 1 exactly at frame 15 and 0 exactly at frame 22.
