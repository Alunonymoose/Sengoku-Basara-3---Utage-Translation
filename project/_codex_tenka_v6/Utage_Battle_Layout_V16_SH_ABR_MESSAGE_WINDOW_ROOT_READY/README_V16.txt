Sengoku BASARA 3 Utage - Battle Message Layout V16
Samurai Heroes "abr" (Western) message window and mission banner

Samurai Heroes ships two battle-HUD masters: id\lsp\jpn\cockpit\* and
id\lspbr\cockpit\*, the abroad build Capcom re-proportioned for Latin text.
All five of its European language folders carry the same abr master. Utage never
shipped in the West, so it only has the jpn master - and its engine's layout
route is hardcoded to jpn. That is why SH's English dialogue overflowed: the
window and banner are sized for Japanese.

V16 copies SH's abr values onto Utage's jpn master for the two message groups
(3_0 dialogue window, 3_1 mission banner), node-for-node by name:

  mission banner   strip 34 -> 44 units tall, rules +/-15 -> +/-22,
                   UV slice 57..91 -> 33..95
  dialogue window  group drops 10 units, left cap and stretch shift 16 units
                   right, Kamon crest restored to its full 256x256 UV

Only position (+0x00), geometry (+0x74) and UV (+0x84) are copied. Offsets +0x30
and +0x38 are left alone: +0x30 is the benign flag from the V8 KOs finding, and
+0x38 is a node link that would point into the wrong tree (Utage has 241 nodes
to SH's 172). Every other resource in each archive is byte-identical.

Patched: rom/{eng,jpn}/id/cockpit1P.arc and rom/{eng,jpn}/id/cockpit2P.arc.
Apply on top of V15. Fully close RPCS3, merge, overwrite, cold boot.
