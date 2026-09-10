Sengoku BASARA 3 Utage English Patch — Free Battle Bounds V4

CUMULATIVE BASE
This ZIP contains the already runtime-confirmed Father Route V3 files plus one new repair:
  PS3_GAME/USRDIR/nativePS3/rom/eng/tenka/tenka_id.arc

WHAT CHANGED
Inside id\lsp\jpn\tenka\tenka_00, only seven Free Battle dynamic stage-name render records were changed.
Horizontal scale: 0.88 -> 0.70
Vertical scale: unchanged at 0.88

WHY
Retail Samurai Heroes and current Utage already agree on the seven English GSM/FIM stage-name strings and their display counts. The Free Battle flow owner free_stage.arc is byte-identical between SH and original Japanese SB3, so it is not where English fitting lives. Utage keeps a different/narrower row presentation while the dynamic text nodes retained the original 0.88 horizontal scale. This patch preserves Utage topology and compresses only the dynamic name width.

ROUTING RULE LOCKED
For every edited ARC family, audit outer/father filesystem references. If a matching /eng/ ARC exists, redirect stale outer /jpn/ father routes to /eng/. Internal resource names containing id\...\jpn or msg\...\jpn are NOT automatically renamed; those remain until separately proven safe.

TEST
1. Fully close RPCS3.
2. Apply this ZIP over the current game root.
3. Cold boot (clear relevant cache for authoritative testing).
4. Open Free Battle and inspect the longest names, especially "Siege of Hasedo Castle".
5. Confirm all seven list rows remain centered vertically, thumbnails/NEW/task icons are untouched, and no stage-name text crosses the right edge.
6. If accepted, move the corresponding screenshot into your Drive fixed folder.
