# Chat Texture Handoff

Use this when a user asks for exact live ARC textures returned as PNGs in chat.

## Command

`python project/tools/chat_texture_handoff.py <arc> --match <resource-substring>`

Example:

`python project/tools/chat_texture_handoff.py tenka\\tenka_id.arc --match tenka_rule`

## Behaviour

- Reuses the latest gallery decode when it already targets the requested ARC.
- Otherwise invokes the canonical `arc_texture_gallery.py` decoder.
- Selects the complete matching PNG family, not just the obvious artwork panels.
- Copies the exact game-view PNGs into `E:\BASARA_WORK\CHAT_TEXTURE_HANDOFFS\...`.
- Renames files to canonical resource basenames without gallery index prefixes.
- Writes `handoff.json` with source ARC, paths, SHA-256 hashes and byte sizes.
- Creates a ZIP containing every selected PNG plus the manifest.
- Writes `E:\BASARA_WORK\CHAT_TEXTURE_HANDOFFS\LATEST.json`.

## Delivery gate

Gallery extraction is not delivery. Do not tell the user the PNGs are visible merely because an internal connector returned image bytes.

Before replying:
1. Check the handoff manifest count.
2. Deliver every requested PNG through an actual user-visible file/link surface.
3. If a family name such as `tenka_rule` was requested, return every matching member unless the user explicitly narrowed the request.
4. Only say files are attached/displayed after verifying that the user-facing response contains working links or attachments.
