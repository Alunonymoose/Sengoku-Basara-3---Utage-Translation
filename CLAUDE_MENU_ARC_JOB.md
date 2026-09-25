# CLAUDE CODE JOB — VERSUS menu.arc TEXTURE QUALITY PASS

## Goal

Audit the current live Versus `menu.arc` and create high-quality production candidates for every texture that is:
- broken
- untranslated where the Japanese is actually consumed at runtime
- translated but visibly low-quality / placeholder-like
- inconsistent with the original Utage visual language

Do not patch custom artwork into the ARC until the exact candidates are approved.

## Live target

Primary live owner:
`E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng\versus\menu.arc`

Pristine JPN reference:
`E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\jpn\versus\menu.arc`

Current known live ENG SHA-256 at handoff:
`e65d2307a5416f5de8ba5abc24041fa1399d1ebbbc65fcaf24a082ae07f96ff6`

Re-hash before work. If the live hash changed, treat the new E: bytes as authority and update the audit baseline.

## Required startup

Read `CLAUDE.md` and all relevant skills under `.claude/skills/` before production work.

Do not begin with image generation.

First:
1. parse live ENG and pristine JPN ARCs
2. inventory/decode all relevant XET/TEX members
3. compare current ENG against real JPN and any proven SH donor
4. inspect relevant LSP/PSL layouts to prove which atlas regions are actually consumed
5. classify each texture
6. rank repair targets by visible value

Classification:
`ACCEPTABLE | UNTRANSLATED | BROKEN | LOW-QUALITY | VERIFY`

Do not treat visible Japanese in an unused/support atlas area as an automatic translation target.

## Hard texture pipeline

For each custom-art target establish:
- LIVE_INPUT
- TARGET_MEMBER
- DECODED_SOURCE
- REAL_REFERENCE
- EDIT_MASKS
- APPROVAL_REQUIRED=true

Then:
1. freeze exact source-space masks
2. generate/draw only isolated art for those masks
3. deterministically composite onto the real decoded live sheet
4. verify all pixels outside masks are identical
5. create `candidate_manifest.json`
6. create a deterministic comparison board from real current ENG + real reference + exact candidate
7. stop that candidate at approval

Never generate a whole atlas/sheet or approval board with an image model.
Never fabricate a JPN/SH/current reference.
Never use a mockup as the production candidate.

## Candidate quality target

Match original Utage presentation quality:
- deliberate hierarchy and spacing
- strong legibility at actual render scale
- styling compatible with the original game rather than generic fan-translation typography
- no crude flat placeholder bars unless they are genuinely part of the original design
- preserve atlas geometry, material fields, alpha/channel behavior and neighboring content

Reject objectively poor candidates before showing them.

## Work family-by-family

Do not try to mutate every bad texture in one giant transaction.

Complete one coherent family at a time:
`audit -> usage proof -> masks -> candidates -> manifests -> comparison boards -> STOP FOR APPROVAL`

Start with the highest-value family based on the fresh audit.

## Existing evidence to verify, not blindly trust

A previous audit found:
- ARC v8, 96 members
- 88 XET textures
- 36 ENG texture payloads differing from pristine JPN
- member 58 is `id\texture\jpn\kessen\kessen_001_ID_HQ`
- `kessen_rule` previously proved only the top two heading bands of member 58 as consumed text regions

Previous physical masks for member 58:
- `(0,0)-(512,64)`
- `(0,64)-(512,128)`

Re-prove these against current live bytes before relying on them.

## First report

Before candidate production, report:
1. current live ARC SHA-256 and member count
2. complete texture classification summary
3. highest-value texture family
4. exact first member/path
5. consumer/layout evidence
6. exact edit masks
7. planned candidate set

Then continue through that family's approval-ready candidates without patching the ARC.
