Sengoku BASARA 3 Utage English Patch - Free Battle Dynamic Bounds V7

This is cumulative over V6. Merge PS3_GAME into the extracted game root and overwrite.

V6 runtime results:
- Quick Battles works.
- The counter suffix Battles works.
- The earlier horizontal-only St_s X edit did not affect dynamic stage text and is superseded here.

V7 changes only id\lsp\jpn\tenka\tenka_00 inside rom/eng/tenka/tenka_id.arc. The seven reusable St_s list templates now use a uniform 0.52 X/Y scale. V6 changed only X while Y stayed at 0.88, and the dynamic text renderer preserved the old size. Setting both components together uses the renderer's uniform text-size path. The seven slots render all 38 stage names, so the correction applies universally across the scrolling list.

The 0.52 value is 59.1% of retail 0.88. Applied to the measured 738-pixel longest title, it predicts about 436 pixels against a roughly 438-pixel row interior. Text height also scales down and must be checked for readability in engine.

GSM, FIM, TNF, CSA, font atlases, Quick Battles, Battles, geometry, and the right-side selected-stage title are untouched. Offline ARC, resource, byte-scope, ZIP, and checksum validation pass. A cold-boot engine test is still required before runtime confirmation.
