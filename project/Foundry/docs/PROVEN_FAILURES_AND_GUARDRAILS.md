# Proven Failures and Guardrails

BASARA Foundry preserves failed approaches because they are often more valuable to future researchers than another success screenshot.

| Failed assumption / workflow | What the project learned | Guardrail |
|---|---|---|
| Treating `\0XET` as Exient/XGS | It is the PS3 MT Framework texture family used here | Start from current Utage TEX/XET evidence |
| Speculative 16-byte ARC entries | Certified Utage ARC v8 uses 80-byte entries | Use the tested reader/writer; fail closed on unknown structure |
| Blanket 8x4/Morton/PS3 swizzle theory | Linear UI fixtures contradicted the blanket rule | Never introduce swizzle without fixture evidence |
| Treating 0x2A as bespoke raw YCbCr | The misleading appearance came from incorrect interpretation/dimensions; current path is BC3 + Kuriimu2 YCbCr shader transform | Use the exact certified transform |
| Byte-swapping BC RGB565 endpoints because the PS3 container is big-endian (2026-09-23/24) | Runtime-disproven on title_004 (green/magenta) and menu.arc member 58 (navy plate); swapped+no-shader decode of 0x2A merely *looks* legible | Standard DXT payload order; judge 0x2A in display space through the shader; `utage_xet.byte_order_evidence` preflight refuses swapped targets |
| Writing display RGBA straight into 0x2A (`xetenc.py`, 2026-09-24) | Valid BC3 bytes with the wrong channel meaning: untouched blocks look right, new lettering renders magenta/cyan/green | Only the YCbCr writer may touch 0x2A; `xetenc.py`/`xet3.py` quarantined |
| Calling identity patches and encode→own-decode round trips "validation" | Identity never calls the encoder; a writer agrees with its own decoder | Colour-regression fixture judged through the game shader + final-ARC re-extract + cold boot |
| Fixing a runtime bug on an unmerged hotfix branch | The title_004 endian hotfix sat on an orphan branch while the primary branch kept the bug | Port runtime fixes to the primary branch the same day and record the supersession in canon |
| Treating 0x2B as normal RGBA or a simple G/A swap | Hidden R/B semantics matter | Preserve RBxG base+mask representation |
| Assuming `rom/jpn` is pristine Japanese | It can contain English/shared content | Hash/name/location are classification evidence, not semantic proof |
| Using a pristine Japanese texture as default incremental base | Can revert already-correct English art | Fresh live target is the preservation base |
| Matching-name Samurai Heroes transplant | Same name does not prove ownership/layout/format compatibility | Verify role, format, display companions and owner family |
| Patching only one duplicate owner | Shared runtime families can load another copy | Resolve/synchronize proven owner families |
| “ARC contains resource” = runtime owner | Presence does not prove effective provider | Use controller/load/registration/runtime evidence |
| Generating a full-screen mockup first | Produces attractive pixels that may be impossible to graft safely into the real atlas | Decode live resource -> prove region -> isolated art -> exact candidate -> derived mockup |
| Showing whatever image generation returns | Bad crop, lettering, UI chrome or transparency can poison the production stage | Apply objective candidate-quality gate before user review |
| Regenerating art after approval | The built asset no longer matches what was approved | Freeze approved candidate identity/hashes |
| Validating the pre-encode PNG | Compression/channel/graft errors can appear only in the stored final resource | Re-extract and decode from the finished ARC |
| Calling a rebuilt file “root-ready” | Rebuilt does not imply correct install path or clean payload set | Package actual final files at game-root paths with manifest |
| Treating historical Drive/checkpoint bytes as live | Regresses later fixes | Fresh uploaded/current live bytes win for mutation |
| Broad speculative testing | Can consume time without discriminating hypotheses | One claim, one smallest reversible test, explicit expected outcomes |
| Using latest Kuriimu2 source without pinning | Current master has materially different PS3 TEX code from the historical revision proven by this project; the current PS3 loader path observed on 2026-09-25 starts mip iteration at 1 and then consumes `mipData[0]`, so source freshness is not equivalent to proven compatibility | Pin the exact proven Kuriimu2 revision/build for production and review upstream changes before adopting them |
| Synthetic roundtrip = Capcom format proof | Internal consistency does not prove retail semantics | Promote only with real fixture/runtime evidence appropriate to the claim |

## Why this document exists

Future contributors and AI agents should not have to repeat these dead ends. When a new experiment disproves an assumption, add it here with the replacement rule and evidence scope.


| Failed assumption / workflow | What the project learned | Guardrail |
|---|---|---|
| Generic PS3 zlib window 14 can be copied from REvilLib into Utage | Live ENG+JPN census found every compressed Utage member uses CMF 0x78 / window 15 | Prefer game-corpus evidence over a generic platform profile |
| `rArchive` entry necessarily contains an embedded ARC binary | Utage's 117-per-route `rArchive` entries are raw ARCS/SCRA child manifests that point at flattened parent resources by class/path hash | Inspect payload magic and resolve ARCS/SCRA before treating an `.arc`-typed resource as a nested container |
