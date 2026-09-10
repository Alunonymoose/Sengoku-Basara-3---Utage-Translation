# Artwork and codec notes

New lettering and stamp masters were generated with built-in ImageGen; no local
font renderer was used to invent replacement lettering. The project copies are:
- menu_lettering_master.png: nine coloured brush wordmarks.
- menu_lettering_key.png: the same sheet on a chroma-key background.
- menu_lettering_sprites.png: extracted sprites used by the native texture build.
- name_lettering_master.png: seven high-contrast white-on-black name rows.
- stamp_master.png: CLEAR and GET! red/gold plaques.

Prompt set:
1. Create nine separated rows of English game UI brush lettering with crisp ivory
   outlines and dark keylines. Exact text and palette: HEROES' STORY crimson/gold;
   UNIFICATION gold/blue; JAPAN'S EVENT teal/jade; VERSUS cobalt/crimson;
   QUICK BATTLES orchid/jade; PLAYER 1 icy white/blue; PLAYER 2 icy white/red;
   DEPLOY orange/red; BATTLE ivory/red. Request transparent alpha and no extra text.
2. Edit that exact sheet, preserving lettering and colours, to replace the cloudy
   backdrop with uniform #FF00FF, including letter holes. No extra lettering.
3. Seven separate rows, bold upright readable white serif English names on pure
   black: Shingen Takeda; Hisahide Matsunaga; Sorin Otomo; Kazumasa Sogo;
   Kanenaka Shichijo; Buddha-Faced Kumahachi; Motosuke Kunishi. No decorations,
   gradients, outlines or additional text; strong strokes for small-size reading.
4. Two separate lacquer-crimson and antique-gold rectangular success plaques,
   gently tilted counterclockwise, exact text CLEAR and GET!, intact borders,
   no Japanese, no extra text. Request a magenta chroma-key backdrop.

Generated backgrounds did not consistently follow the requested alpha/key colour.
The chosen master sprites were isolated, cropped, resampled and encoded during
texture integration. Stamp boundaries were isolated from the generated backdrop.
The new five mode logos are fitted to equal 80-pixel ink height inside original
112/120-pixel slots; their native frames are not resampled or regenerated.

Important correction to V2's preview assumption: raw BC3 RGBA is not display RGBA.
These assets decode consistently with R=Cr, G=opacity, B=Cb, A=luminance. The YCbCr
conversion in common.py reproduces the Japanese atlas palette shown in the user's
texture editor. V3 previews and integration use that conversion. RGB must remain
meaningful even when the BC3 alpha/luminance channel is zero (e.g. black outlines).
Do not treat the native BC3 A channel as conventional transparency.

Archive resources are replaced by name/index inside current live archives, with
all non-target compressed blobs and LSPs preserved. Original Japanese resources
are read-only. See the build scripts and release/INDEPENDENT_CHECK.json for scope.

The previews are decoded texture evidence, not RPCS3 screenshots.
