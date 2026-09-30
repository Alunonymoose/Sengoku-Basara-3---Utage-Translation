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

## 2026-09-30 animation parent/trailer semantics

The final signed word of each animation record is structural parent/group linkage, not a temporal offset.

Evidence:
- title groups often use the first sibling record as the parent of later siblings;
- those animation-parent relationships do not match the target sprites' node-parent hierarchy;
- tenka/top_00 child tracks under the same group contain deliberately staggered absolute clip-frame ranges:
  - Shing 10..15
  - Soubi 20..25
  - Basara 30..35
  - Guide 40..45
  - Settei 50..55
- subtracting or accumulating parent durations would destroy that intended cascade.

Therefore:
- animation_tree remains valid for scope/group traversal;
- descendants are sampled using the same selected clip frame, clamped only to their own duration;
- parent_animation must not be used as an implicit frame offset.

This also matches the EBOOT runtime cSprAnim fields mParentID/mpParent: parentage is an object relationship, while key timestamps already provide timing.

## 2026-09-30 interpolation fidelity rule

Interpolation code 5 remains unproven.

Observed facts:
- it is used on position/scale tracks;
- transform keys do not contain hidden tangent/control values in their spare vector components;
- generic MT Framework binaries expose easecurve/hermitecurve data types, but no direct evidence yet ties PSL code 5 to either evaluator.

The harness currently approximates code 5 with smoothstep for visualization only.

Any selected animation subtree containing code-5 keys now emits an explicit animation warning:
`interpolation code 5 is approximated as smoothstep; exact MT Framework curve is not yet proven`

This prevents approximate renders from being mistaken for exact runtime reproduction.


## 2026-09-30 follow-up: duplicate sprite IDs and inherited orphan target

Full live ENG sweep after sprite-ID target correction:

- 4,075 ARCs parsed;
- 87 PSL layouts parsed;
- 14,859 nodes;
- 7,954 animation records;
- **0 layout failures**.

### Duplicate node IDs

Serialized sprite IDs are normally unique, but a small number of layouts intentionally reuse an ID. The resolver must therefore not assume global uniqueness.

Proven cases:

- cockpit1P ID 326: `Nyusin` and group `0_0_9`. Animation `Kao1set` targets 326; its child tracks target descendants of `0_0_9`, disambiguating the group.
- vs_cockpit ID 102: groups `2_0` and `3`. Sibling records `CPU_item_1P` and `CPU_item_2P` both target 102; two records/two duplicate instances preserve serialized order.
- vs_cockpit ID 48: `Flag0_0` and unrelated group `1_2`. `Flag0_1` resolves to the same flag family.

The current resolver therefore uses, in order:

1. unique ID match;
2. ordered repeated-record/repeated-node mapping when counts match;
3. descendant-track ancestry for group animations;
4. conservative family-name affinity;
5. unresolved/fail-closed otherwise.

### Utage top_00 target ID 102 is a benign inherited orphan

Utage `id\\lsp\\jpn\\tenka\\top_00` contains two animation records targeting sprite ID 102:

- `8_0`
- `4_0`

Utage has no sprite node ID 102.

The corresponding Samurai Heroes layout
`id\\lsp\\abr\\tenka\\top` **does** contain:

- node index 79, ID 101, name `4`;
- node index 80, ID 102, name `4_0`, type 4, position (0,389);
- child sprites ID 103/104/105 named `Mess`.

Samurai Heroes also carries the same target-102 tracks:

- `8_0 -> 102`
- `4_0 -> 102`

Therefore Utage retained animation records for the old SH `4_0` message/menu group after removing that group from the Utage node table. These unresolved targets are inherited dead references, not parser corruption and must remain ignored/fail-closed rather than remapped to array index 102.


## 2026-09-30 follow-up: baseline display state and interpolation ownership

### Serialized baseline display/shake candidates

A full 87-layout / 14,859-node sweep of the live ENG tree gives:

- node +0x30: only 0 or 1
  - 6,779 nodes = 1
  - 8,080 nodes = 0
- node +0x34: 0 on all 14,859 nodes

Combined with the Utage EBOOT cLayoutSprite reflection fields `mIsDisp` and
`mIsShake`, and with the semantic distribution of +0x30 (ordinary title/loading
sprites enabled, large banks of optional/common/menu-state sprites disabled),
+0x30 is strongly supported as the serialized default-display flag.

+0x34 is exposed as `default_shake` for forensic completeness, but remains
weaker evidence because the current live corpus never serializes a non-zero value.

Important runtime distinction: default display is not permanent draw eligibility.
2,522 animation records with keyed tracks target nodes whose serialized +0x30
default is 0. Common examples include cursors, difficulty labels, menu highlights,
2P prompts and Tenka menu entries. Higher-level UI/clip playback therefore activates
initially-hidden sprites outside the ordinary keyed display channel. The renderer
must not blindly suppress a deliberately selected animation target merely because
its resource default is hidden.

### Interpolation mode belongs to the left/outgoing key — strong structural evidence

Across 10,510 keyed tracks:

- code 3 is overwhelmingly dominant;
- code 0 and code 5 occur on first, interior and final keys;
- mixed two-key transform tracks provide the most useful direction evidence.

Examples:

- tenka_tassei `tekichu_2` scale 10.0 -> 1.6 over 10 frames has key codes 3 -> 0.
  Interpreting the left key as segment owner produces an ordinary animated shrink;
  right-key ownership would hold at 10 then jump to 1.6.
- tenka_tassei `sensu_mask` position 9 -> 5 over 48 frames has codes 0 -> 3.
  Left-key ownership naturally gives a held/step offset.
- gallery/title entrance motions such as -50 -> 0 over 10 frames use 5 -> 3.
- tenka_japmap `Map_Base` scale 2.5 -> about 1.0 over 13 frames uses 5 -> 3.

This strongly supports the harness's existing left-key segment ownership:

- code 0: hold/step behavior;
- code 3: ordinary linear interpolation;
- code 5: an ease-family interpolation.

The exact code-5 ease evaluator is still unproven. The current smoothstep
approximation must remain labelled approximate.

Engine-side supporting context: the Utage EBOOT contains `Depth (Linear and Ease)`,
`Ease`, and `mEaseCurve` strings, while public MT Framework reverse engineering
shows `MtEaseCurve` as a two-float structure distinct from the much larger
8-point `MtHermiteCurve`. This supports an ease interpretation but does not bind
PSL code 5 to a specific mathematical curve.


## 2026-09-30 follow-up: untextured type-0 / type-1 quad rendering

A full node-type survey across all 14,859 live PSL nodes identified a large class
of untextured geometry that the earlier renderer omitted entirely.

### Type 1 — untextured per-vertex RGBA quad

In the current live corpus, type-1 nodes are untextured geometry and strongly match
four-corner AARRGGBB interpolation.

Examples include:

- loading-screen black -> transparent edge fades;
- common/menu `Obi` and `Message` vertical gradients;
- result-screen shadow strips;
- quest white/green overlay gradients;
- story background-colour panels;
- title colour-wall quads.

A direct renderer test on `loading/black_03_hidariue` used its corners

- TL = FF000000
- TR = 00000000
- BL = FF000000
- BR = 00000000

and produced the expected continuous left-black -> right-transparent fade over a
magenta diagnostic background. This validates the existing TL/TR/BL/BR bilinear
corner order for this untextured type.

### Type 0 — conservative solid-color0 subset

Type-0 nodes are also untextured geometry in almost all cases, but their material
semantics are not uniformly equivalent to type 1.

The safest, strongly evidenced subset is:

- all four serialized colours identical; or
- color1/color2/color3 remain untouched FFFFFFFF defaults.

For those nodes, color0 behaves as the whole-quad colour/alpha.

Strong examples:

- `com/fade/Black`
- `com/wipe/Wipe`
- Capcom/loading black backgrounds
- cinematic black bars
- translucent common/pause backdrops
- thin UI rules/lines
- title/kakusyu black overlay

The harness now renders only this proven type-0 subset as a solid color0 quad.
Type-0 nodes with meaningful non-default secondary corner colours remain fail-closed
because their shader-specific gradient/filter semantics are not yet fully mapped.

### Fade runtime-style regression

`basara.arc -> id\\lsp\\com\\fade -> Ani 0_0` was rendered at frames 0/30/60
over an opaque magenta diagnostic background:

- frame 0: every sampled pixel = (0,0,0,255)
- frame 30: every sampled pixel = (127,0,127,255), i.e. approximately 50% black
- frame 60: every sampled pixel = magenta background; the zero-alpha Black quad is skipped

The Black node is type 0, has no texture, and its color0 track is
FF000000 -> 00000000 over 60 frames. This is direct evidence that the new
untextured solid-quad path reproduces the intended fade behaviour.

Diagnostic outputs:
`E:\\BASARA_WORK\\jobs\\utage_harness_anim\\untextured\\fade_0.png`
`E:\\BASARA_WORK\\jobs\\utage_harness_anim\\untextured\\fade_30.png`
`E:\\BASARA_WORK\\jobs\\utage_harness_anim\\untextured\\fade_60.png`
`E:\\BASARA_WORK\\jobs\\utage_harness_anim\\untextured\\loading_type1_19.png`
