# Foundry executable-state milestone â€” 2026-09-30

## Added

- rebuildable SQLite Foundry Graph over current ENG/JPN/SH corpora;
- SHA-256 identity for indexed files and ARC resources;
- XET metadata indexing without changing production bytes;
- cross-route JPN comparison and cross-archive official-SH donor recognition;
- current RPCS3 log path ingestion;
- machine-readable sign-off certificates with automatic stale detection;
- whole-tree texture QA triage JSON/CSV;
- single `foundry` command front door;
- texture-book PDF generation as the standard "show me textures" handoff;
- pinned external-oracle lock for research/tool deltas.

## Initial live build

The first live graph build indexed:
- ENG: 4,082 files, 4,075 ARCs, 61,494 resources, 47,650 textures, 0 ARC parse failures;
- JPN: 4,075 files, 4,075 ARCs, 60,893 parsed resources, 47,227 textures, 2 intentional fail-closed trailer warnings;
- Samurai Heroes: 2,131 files, 2,118 ARCs, 20,344 resources, 14,063 textures;
- current RPCS3 log: 1,091 unique nativePS3 paths.

After cross-archive donor matching, 20,431 current ENG resources had exact official-Samurai-Heroes payload matches.

## Migrated sign-offs

Machine-readable certificates were created for:
- `rom/eng/sound`
- `rom/eng/demo`
- `rom/eng/versus`
- `rom/eng/select`

All were VALID at creation time.

## Safety

SQLite remains a rebuildable cache. Fresh live bytes remain production authority. Heuristic texture scores never authorize mutation.