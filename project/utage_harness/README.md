# Utage Harness V0

A BASARA-specific offline verifier and partial 2D runtime for Sengoku BASARA 3 Utage.

This is **not** a PS3 emulator and does not claim to reproduce PPU/SPU/RSX execution.
It is a fast pre-runtime gate for the asset classes we repeatedly modify.

## Current capabilities

- Parse real ARC v8 files through the current Alrummi3 parser.
- Re-read/decompress exact final ARC members rather than trusting source PNGs.
- Decode PS3 XET display output through the runtime-proven 0x2A YCbCr contract.
- Inventory PSL/LSP layouts and their texture/node-name relationships.
- Compare two ARCs at decompressed-member level.
- Render explicit multi-layer 2D scenes from ARC members.
- Apply the project 2x logical-to-physical placement rule when requested.
- Parse RPCS3 RRC v6 captures conservatively from active replay memory references.
- Exact-match active RRC payloads directly against decompressed ARC members,
  including whole resource, 20-byte XET skip, mip-0-to-EOF and exact mip-0 level bytes.

## Commands

```powershell
python utage_harness.py arc-report <arc> [--json report.json]
python utage_harness.py preview <arc> <member-name-or-index> out.png
python utage_harness.py compare-arcs before.arc after.arc
python utage_harness.py layouts <arc>
python utage_harness.py render-scene scene.json out.png
python utage_harness.py rrc-info capture.rrc.gz
python utage_harness.py rrc-match-arc capture.rrc.gz live.arc
```

## Scene format

```json
{
  "size": [1280, 720],
  "background": [0, 0, 0, 255],
  "logical_scale": 2.0,
  "layers": [
    {
      "archive": "E:/.../title.arc",
      "member": "id\\texture\\jpn\\title\\title_004_ID_HQ",
      "source": [0, 0, 512, 256],
      "dest": [50, 30, 512, 256],
      "logical": false,
      "opacity": 1.0
    }
  ]
}
```

## Evidence boundary

Harness success means the resource is structurally readable and the supported
offline rendering contract behaves as expected. It does **not** replace the
project's final RPCS3/PS3 runtime acceptance test.

RRC matches prove byte correspondence to command-referenced captured memory.
They do not by themselves prove sole filesystem ownership/provider precedence.

PSL node source rectangles and placement are still not decoded automatically.
Until that format is cracked, scene geometry is supplied explicitly. The
`layouts` command still gives the game's own node names and texture links.

## Authority

The harness imports the current canonical parser/codec from this repository:
- `project/Alrummi3/alrummi3_core.py`
- `project/Alrummi3/layout.py`
- `project/texture_tools/xet_ps3_2026-09-25/xet_ps3.py`

It intentionally does not copy retail game payloads into Git.
