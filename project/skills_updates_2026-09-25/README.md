# Account skill updates — 2026-09-25

Cloud sessions can read but not save the Utage skills in the claude.ai account.
These two files are corrected full replacements; paste each over the
matching skill (Settings → Skills, or ask Cowork/Claude Code to save them):

| Skill | What changed |
|---|---|
| `utage-texture-pipeline` | §1 BC payload byte order is standard (big-endian endpoint rule disproven at runtime); §2 0x2A resolved as standard BC3 + YCbCr, legacy-damage census/repair; §3 `utage_xet` is the canonical codec, `xetenc.py`/`xet3.py` quarantined; queue + disproven list updated |
| `utage-menu-arc-texture-job` | member 58 v3 status; cursor "cyan material" was an artefact; tools point at `utage_xet`; encode step uses `xetcli.py arc-graft` |

`utage-session-start` and `utage-text-pipeline` need no texture change
(session-start's tool-routing row "Textures / text → the pipeline skills"
now resolves to the corrected texture skill).

## 2026-09-26 addendum — `basara` core toolchain

Add this line to the tool-routing table of **utage-session-start** and to §2
of **utage-text-pipeline** (it supersedes `gsm_tools.py`/`arc_tools.py` for new work):

> **All byte-level work goes through `basara`** (`project/basara`, `pip install -e project/basara[test]`):
> `basara msg tables|show|census`, `basara catalog export|lint|import`, `basara tex …`,
> `basara build|install|rollback`. Patchsets replace per-job scripts and ZIPs; `install`
> implements the backup-before-write rule. See `.agents/skills/basara-core/SKILL.md`.
