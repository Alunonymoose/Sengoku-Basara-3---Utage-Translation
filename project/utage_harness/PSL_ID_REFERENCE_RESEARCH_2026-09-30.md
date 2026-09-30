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
