Sengoku BASARA 3 Utage - Battle Dialogue V15
Mission-local ASCII font, all English mission message sets

WHAT WAS WRONG
V10/V11 removed each mission set's local font resources (TNF .fnt, CSA .asc
and the glyph atlas .tex pages) on the theory that Utage would fall back to the
global msgscii font the way Samurai Heroes does.  It does not.  With no local
.fnt the engine cannot resolve the set at all, so no battle dialogue was drawn.
The RPCS3 log shows this directly: a single failed lookup for
  /dev_bdvd/.../nativePS3/msg/m019_15/jpn/m019_15.fnt
and then a fallback attempt to load message set m000_00, which does not exist.

THE FIX
Every English text set that already works in Utage (id_pause, id_result,
id_tenka, id_brief) carries its own private copy of the global ASCII font under
its own resource names.  V15 gives all 606 remaining battle message sets the
same shape, rebuilt from the pristine Japanese archives:

  TNF msg\<set>\jpn\<set>          = global ASCII TNF (184 glyphs, 2 pages)
  CSA msg\<set>\jpn\<set>          = global ASCII char->glyph table
  XET msg\<set>\jpn\<set>_00_ID_HQ = global ASCII atlas page 0
  XET msg\<set>\jpn\<set>_01_ID_HQ = global ASCII atlas page 1
  GSM/FIM (main and _r)             = exact Samurai Heroes English payloads
  stage script + army name plates   = byte-identical Utage originals

Stale Japanese atlas pages 02+ are dropped; the ASCII TNF encodes its page in
the high byte of each glyph id and never references a page above 1.

The two sets already converted by V14 (m000/pl003 and m034/pl015) are unchanged
and are not included here.

INSTALL
Fully close RPCS3, merge PS3_GAME into the Utage game root, overwrite, then cold
boot.  Do not use a save state for the first test.

KNOWN LIMITATION
The Samurai Heroes text is installed wholesale, so message ids drift slightly
against Utage's own script (m019/pl015: SH has 407 messages, Utage 667; the id
columns run parallel but diverge by one from about message 137).  Utage-only
lines have no Samurai Heroes source and will be blank.
