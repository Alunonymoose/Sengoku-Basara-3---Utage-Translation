# Kuriimu2 integration notes

Alrummi 3's ARC loader follows the public Kuriimu2 MT Framework plugin source:

- `plugins/Capcom/plugin_mt_framework/Archives/MtArcSupport.cs`
- `plugins/Capcom/plugin_mt_framework/Archives/MtArc.cs`

Upstream: <https://github.com/FanTranslatorsInternational/Kuriimu2>

The loader now follows the source's platform rules for the formats relevant to
batch inspection: `\\0CRA` is the PlayStation/Xbox big-endian form, version 9
is identified as Switch, and other forms default to little-endian. It also
recognizes the extended-name entry layout used by little-endian archives,
retains the packed decompressed-size fields correctly, and displays the known
`.msg`, `.mif`, `.asc`, `.fnt`, `.tex`, and `.lsp` type hashes.

Alrummi 3 keeps its Utage-specific XET/BC3 and confirmation logic in Python;
it does not silently replace the user's source archive. Kuriimu2 remains the
upstream reference for broad format/plugin behavior, while this app adds the
offline AI review workflow.

