# PSL sprite-ID reference checkpoint — 2026-09-30

Status: **strongly supported by live Utage regression**.

## Core finding

Several PSL fields that look like node indexes are actually serialized sprite IDs.

Confirmed:
- animation record target -> sprite ID at node field 0x50;
- link_40 -> sprite ID when used as a mask/reference;
- parent field 0x38 remains a real node array index.

The parser now exposes node_id and resolves animation targets/mask links through node IDs.

## Animation-target regression

Test set: 16 live layouts from title.arc, result_id.arc, quest/menu.arc and versus/menu.arc.

Across 888 target-bearing animation records:
- 886 resolve to a unique serialized sprite ID;
- only 2 remain unresolved;
- both exceptions are in tenka/top_00;
- both use target ID 102;
- the records are named 8_0 and 4_0;
- node ID 102 does not exist in that layout.

Do not fall back to array index 102: index 102 is an unrelated Suji node.

The two target-102 records are therefore treated fail-closed as a virtual/dynamic target exception pending runtime proof.

## Mask-link regression

Across the same 16 layouts:
- 47 nodes have nonnegative link_40;
- 41 resolve by sprite ID to type-5 mask nodes;
- the remaining 6 resolve to non-mask targets and must remain generic links.

Important examples fixed by ID resolution:
- mode_select top_00 / bottom_00 / bottom_copy_00 -> sprite ID 55 -> node index 16 MASK_00;
- soubi_00 Wep_K -> sprite ID 467 -> type-5 mask;
- result_00 Base/Waza -> sprite ID 598 -> node index 591 Mask.

Treating link_40 as an array index silently lands on unrelated nodes in these cases.

## Parent-reference control test

The parent field at 0x38 behaves differently:
- parent values consistently produce sensible hierarchy when treated as array indexes;
- converting parent values through node IDs frequently lands on semantically unrelated sprites.

Therefore parent traversal must stay index-based.

## Harness behavior

Current branch commits:
- b6f189e — animation targets resolved by sprite ID;
- 9941bde — mask links resolved by sprite ID;
- 1ff7c9d — harness uses ID targets, fail-closed clip selection, and dominant/final RRC surface selection.

Regression artifact:
E:\BASARA_WORK\jobs\utage_harness_anim\PSL_ID_REFERENCE_REGRESSION_2026-09-30.json

## Full-tree regression — 2026-09-30

### Samurai Heroes ENG
Root: `E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng`

- 2,118 ARCs parsed
- 79 PSL layouts
- 6,687 nodes
- 3,194 animation records
- **0 layout parse failures**
- 2 unresolved animation targets, both in `tenka_narration01` (IDs 201/202)
- 0 duplicate node IDs
- 24 nonnegative link_40 values
- 16 proven type-5 mask links

### Utage live ENG
Root: `E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng`

- 4,075 ARCs parsed
- 87 PSL layouts
- 14,859 nodes
- 7,954 animation records
- **0 layout parse failures**
- 8 unresolved animation targets
- 10 duplicate node IDs
- 202 nonnegative link_40 values
- 175 proven type-5 mask links

The parser therefore closes successfully across all 166 discovered layouts in the two English trees.

Duplicate sprite IDs are real data, not parser corruption. ID resolution must be fail-closed unless exactly one node owns the ID.

The remaining Utage unresolved animation targets split into:
- repeated virtual/missing target ID 102 in tenka/top_00;
- targets whose IDs are duplicated in cockpit layouts.

No scalar/control field in the examined ambiguous animation records supplied a proven parent/scope ID, so duplicate targets must not be guessed by first-match, last-match, name similarity, or array index.

Regression JSON:
- `E:\BASARA_WORK\jobs\utage_harness_anim\SH_ENG_FULL_PSL_SWEEP_2026-09-30.json`
- `E:\BASARA_WORK\jobs\utage_harness_anim\UTAGE_ENG_FULL_PSL_SWEEP_2026-09-30.json`

## Resolution provenance refinement

The sweep now distinguishes exact unique-ID resolution from heuristic duplicate-ID resolution.

Current full-tree totals:

### Utage ENG
- 4,075 ARCs
- 87 PSL layouts
- 14,859 nodes
- 7,954 animation records
- 0 layout parse failures
- **4 unresolved animation targets**: all `missing_id` cases from the repeated tenka/top_00 ID-102 pair
- **4 heuristic animation targets**
  - 1 `duplicate_descendant_scope`: cockpit1P `Kao1set` -> node `0_0_9`; all six descendant tracks live beneath that candidate
  - 2 `duplicate_order_pair`: vs_cockpit `CPU_item_1P/2P`; exactly two records target the duplicated ID and exactly two nodes own it, paired in serialized order
  - 1 `duplicate_name_affinity`: vs_cockpit `Flag0_1` -> `Flag0_0`; useful but weaker evidence and must remain labelled heuristic
- 10 duplicate node-ID occurrences
- 202 nonnegative link_40 references
- 175 proven type-5 mask links

### Samurai Heroes ENG
- 2,118 ARCs
- 79 PSL layouts
- 6,687 nodes
- 3,194 animation records
- 0 layout parse failures
- **2 unresolved animation targets**, both `missing_id` in `tenka_narration01` (IDs 201/202)
- **0 heuristic animation targets**
- 0 duplicate node IDs

The audit deliberately keeps heuristic resolutions visible even when they produce a usable target. A zero unresolved count must not be interpreted as equivalent to unique-ID proof.
