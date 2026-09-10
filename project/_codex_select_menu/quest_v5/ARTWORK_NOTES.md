# V5 menu artwork

Retains the approved Heroes' Story, Unification, Japan's Event, Versus and Quick Battles designs from the V4 keyed master. Each native sprite is now downsampled once from its master with uniform aspect ratio; no independent horizontal or vertical stretching. Normal and selected states share proportions. The seven normal menu shadow offsets were reduced from (4,5) to (1,1.5).

Generated Gallery, Options and Locked in this task using ImageGen, referencing the approved menu lettering master. Selected originals are `additional_master.png` and `additional_key.png` beside this note. No locally rendered font replacements were used.

Generation prompt: Use the supplied lettering only as a style reference. Create a NEW sheet with exactly THREE separate wide horizontal wordmarks in three evenly spaced rows. Row 1 exact text GALLERY, antique gold transitioning to warm copper-red. Row 2 exact text OPTIONS, teal blue transitioning to plum purple. Row 3 exact text LOCKED, ivory-white and silver grey. Match the bold readable English brush-calligraphy of the reference, crisp ivory edge and a restrained clean black keyline. Less tiny distressed detail: solid strong interiors, clean curves, no detached flecks, no long swashes. Preserve natural letter proportions. No frames, icons, diamonds or other text. All three words complete, large and readable, ample separation. Transparent background with actual alpha. If transparency is unavailable use a single uniform flat pure magenta #FF00FF backdrop with no glow, shadows or gradients.

Keying edit prompt: Keep these exact three wordmarks GALLERY OPTIONS LOCKED unchanged in their lettering, colours, proportions and positions. Replace ALL background, including holes between letters, with perfectly uniform solid pure magenta #FF00FF. No clouds, gradients, glow, drop shadows, noise or background texture. Keep clean hard wordmark edges and their black keyline. This is a game sprite extraction sheet.

Mechanical preparation removes connected magenta background, isolated dust and neighboring-row fragments. The native target cells are cleared completely before placement. The corrected V4 YCbCr/opacity BC3 encoder is retained. Decoded opacity is checked to remain zero wherever each input cell was transparent.

Native-resolution decoded reviews: MODE_DECODED.png and LOCKED_DECODED.png. P2_JOIN_FIT.png reconstructs the compact prompt geometry with the runtime START icon; it is an offline illustration, not an emulator capture. All changes require a fresh game boot for runtime confirmation.
