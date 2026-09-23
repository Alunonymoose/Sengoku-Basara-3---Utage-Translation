# BASARA Foundry Resource Ownership Analyzer

**Version:** 1.0 — 2026-09-23

This is the production payoff from the 2026-09-23 Utage resource-manager reverse engineering.

## What it answers

For every exact runtime resource identity:

`(raw ARC type hash, ASCII-lowercased exact internal path bytes)`

the analyzer finds every ARC provider, fingerprints the stored and expanded payloads, classifies duplicate groups, and — when you provide runtime load/open evidence — identifies the earliest matching provider under the proven **first successful population claim wins** model.

It deliberately does **not** treat filesystem sort order as runtime precedence.

## Run

```bat
python basara_resource_ownership.py "E:\Utage Patching New\PS3_GAME\USRDIR\rom\eng"
```

Better, with RPCS3 evidence:

```bat
python basara_resource_ownership.py "E:\Utage Patching New\PS3_GAME\USRDIR\rom\eng" ^
  --rpcs3-log "RPCS3.log"
```

Or with a curated earliest-registration-first ARC list:

```bat
python basara_resource_ownership.py "E:\Utage Patching New\PS3_GAME\USRDIR\rom\eng" ^
  --load-order "load_order.txt"
```

Search a family:

```bat
python basara_resource_ownership.py "E:\Utage Patching New\PS3_GAME\USRDIR\rom\eng" ^
  --rpcs3-log "RPCS3.log" ^
  --query "charasele_02"
```

## Outputs

`_BASARA_RESOURCE_ANALYSIS/`

- `resource_ownership.json` — complete machine-readable graph/report.
- `resources.csv` — every parsed ARC member.
- `duplicate_classes.csv` — one row per exact duplicate identity.
- `PRIORITY_REPORT.md` — divergent/unresolved classes first, with provider evidence.

## Classification

- `SAFE_IDENTICAL_EXPANDED` — all providers decode to identical expanded bytes.
- `SAFE_IDENTICAL_RAW` — expansion unresolved but raw bytes + flags + sizes are identical.
- `DIVERGENT` — expanded payloads differ.
- `UNRESOLVED_COMPRESSION` — packing cannot be safely resolved enough to compare payloads.

## Hard rules encoded

1. ARC v8 entry stride is 0x50.
2. `entry+0x40` is the raw resource type hash.
3. Exact identity lowercases ASCII path bytes only.
4. `<LANG>` locale abstraction is analysis-only and never used for exact runtime duplicate identity.
5. A zlib failure is **not** interpreted as "therefore raw."
6. Stored-byte differences are not enough to call resources divergent if expanded bytes are identical.
7. Effective-provider claims require supplied order evidence.
8. Co-resident exact typed/path duplicates follow the proven first-successful-population model.

## Important scope

This analyzer tells us which duplicate providers are dangerous and, with runtime order evidence, which provider is likely effective. It does not pretend that a static tree alone proves runtime owner acquisition. Consumer owner-route proof and RPCS3 evidence remain authoritative when available.