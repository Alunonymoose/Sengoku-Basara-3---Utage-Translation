Sengoku BASARA 3 Utage - Battle Dialogue V20 Text Baseline

V19 did not visibly move the dialogue glyphs. Image measurement against the
official Samurai Heroes frame places the remaining offset at 12 pixels at
1920x1080, equal to 8 units in the cockpit's 1280x720 coordinate system.

V20 moves parent dialogue node 3 upward by 8 units. It applies equal opposite
compensation to visual roots 3_0 and 3_1 and all four active 3_0 Y keys. This
preserves the current panel, portrait, name plate, and auxiliary visual world
positions while raising only the parent-level generated-text origin. V19's SH
special-root block is retained. No message, FIM, font, texture, or cockpit2P
resource is modified.

Fully close RPCS3 and cold boot m034/pl015 without a save state. Compare the
same two-line and three-line exchanges. The whole glyph block should move up
12 pixels at 1080p while the panel and portrait remain in their V19 positions.
Verify the third line is clear of the panel bottom and check the mission banner,
health/Basara meters, partner HUD, minimap, and KOs counter.
