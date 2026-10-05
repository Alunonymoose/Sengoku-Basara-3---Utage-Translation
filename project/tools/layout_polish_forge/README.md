# UTAGE Layout Polish Forge v3

Authority root:
E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng

Purpose:
Reproduce and audit live Sengoku BASARA 3 Utage texture consumers from real LSP/PSL layout data rather than judging raw atlases by eye.

Core checks:
1. Layout composition render
2. Layout-referenced texture inventory
3. Custom/current-vs-JPN quality review
4. Crop/overflow and boundary-continuation analysis
5. Provider mismatch analysis
6. Samurai Heroes donor validation
7. Mixed-atlas residual-JPN scan
8. Whole-resource JPN-exact scan
9. Versus waza2 42px row registration audit

Hard rules:
- LSP/PSL consumer rectangles are the truth surface.
- Physical atlas coordinates follow the proven 2x layout scale.
- Do not flag Japanese in dead/unused cells.
- Do not flatten route-specific provider variants just because an internal texture name matches.
- Do not donor-swap by internal name alone; verify semantic equivalence in the actual consumer.
- Engineer fixes may reuse exact existing English pixels, official semantically-equivalent donor bytes, or canonical provider bytes.
- New/redrawn art is Artist-window only.
- Every install is backup -> source-hash gate -> staged rebuild -> parse/decode verification -> live install -> post-install hash/render proof.

User locks:
- kessen_008_ID_HQ and kessen_009_ID_HQ Japanese plaques are intentional and must not be changed.
- title_012_ID_HQ and title_015_ID_HQ Utage/宴 branding is intentional and must not be changed.

Current truth:
See CURRENT_POLISH_QUEUE.json and A_Z_QA_CHECKPOINT_V14_2026-10-05.json in the job folder.
