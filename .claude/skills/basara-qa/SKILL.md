---
name: basara-qa
description: Direct QA for Utage ARCs, folders, ZIPs, textures, text and layouts. Inspect supplied bytes directly, classify only evidence-backed defects, and identify exact repair targets.
---

# Utage QA audit

Apply the BASARA production contract first.
QA is evidence collection unless the user explicitly asks to transition into repair.

## Direct inspection

Open and inventory supplied files yourself.
Do not require the user to preprocess, export, map or build contact sheets when the current environment can do it.

Use current live bytes as truth.
Historical maps/reports accelerate navigation but do not override the live build.

## Audit layers

1. ARC integrity — parseability/version/count/ranges, duplicate paths, divergent copies
2. Text — untranslated Japanese, truncation, malformed English, control-token damage
3. Textures — baked Japanese, low-quality replacements, compression/channel problems, typography mismatch
4. Layouts — LSP/PSL source rects, geometry, bounds, baselines and donor parity
5. Cross-resource consistency — English payload + Japanese display data, stale siblings, incomplete donor sets
6. Runtime evidence — screenshots/logs/RRC where supplied

Do not call raw storage-channel weirdness visual corruption without correct decoding.
Do not call static dimensions runtime clipping proof.

## Texture classification

For every relevant decoded texture classify:
- ACCEPTABLE / LEAVE ALONE
- UNTRANSLATED
- BROKEN
- LOW-QUALITY / PLACEHOLDER
- NEEDS RUNTIME CONFIRMATION

For ugly or untranslated atlas work, prove which source rectangles are actually consumed before defining edit masks.

Prefer family-by-family repair so one visual language and one approval gate can be maintained coherently.

## Finding contract

For each real finding record:
`severity | confidence | ARC/member | defect | evidence | likely fix | runtime test`

Severity:
`P0 | P1 | P2 | VERIFY`

Confidence:
`PROVEN STATIC | PROVEN RUNTIME | STRONGLY SUPPORTED | SUSPECT`

Prefer a smaller set of high-confidence findings over large heuristic noise.

## Menu/Versus texture jobs

When auditing a live `versus/menu.arc`:
- decode all XET/TEX resources using the proven format path
- compare against real pristine JPN and proven SH donors where relevant
- inspect kessen LSP/PSL consumers before editing atlas regions
- distinguish translated-but-ugly art from unused Japanese/support atlas content
- never translate unused atlas pixels merely because Japanese is visible in the decode
