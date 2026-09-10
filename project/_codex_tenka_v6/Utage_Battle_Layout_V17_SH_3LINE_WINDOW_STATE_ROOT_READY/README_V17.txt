Sengoku BASARA 3 Utage - Battle Layout V17
Samurai Heroes' three-line message-window animation state

The cockpit LSP's animation section is a flat sequence of blocks, one per entry
in the name table after the node array. The first three groups are the message
window's size states:

  Ani 0_0_0  Mess1 Mess3 Mess4 Name Kamon   1-line window
  Ani 0_0_1  Mess1 Mess3 Mess4 Name Kamon   2-line window
  Ani 0_0_2  Mess1 Mess3 Mess4 Name Kamon   3-line window

Utage and Samurai Heroes are byte-identical through Ani 0_0_1 and into
Ani 0_0_2's Mess1/Mess3 tracks. They diverge on Mess4: SH carries a full
448-byte track where Utage has a 104-byte stub, and SH keys scale on Name where
Utage has none. Capcom authored that third state for the Western release. Utage,
whose own dialogue never exceeds two lines (checked: 0 three-line pages in every
mission set, against ~120 per set in SH), never got it - so the third line of
Samurai Heroes' English fell out of the box.

V17 replaces Utage's whole Ani 0_0_2 group with SH's: 2736 -> 2784 bytes. Blocks
are self-describing and walked in order - no offset table references them - so
the group can change length and everything after simply shifts. Node data, the
name table, and the node/animation counts are untouched, and every other
resource in the archive is byte-identical.

cockpit2P is deliberately NOT patched: SH's 2p Ani 0_0_2 is smaller than Utage's
(2632 vs 2736 bytes), so porting it would regress split-screen.

Apply on top of V15 and V16. Close RPCS3 and any ARC editor holding
cockpit1P.arc, merge, overwrite, cold boot.
