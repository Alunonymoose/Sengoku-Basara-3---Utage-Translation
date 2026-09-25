---
name: basara-core
description: Use for ANY Sengoku BASARA 3 Utage byte-level work (ARC, XET/TEX textures, GSM/FIM/TNF/CSA text, PSL layouts, installs). The `basara` package is the single implementation of every format; never write a new parser, encoder or install script.
---

# basara core — use it, don't re-implement it

Install once: `python -m pip install -e project/basara[test]` → `basara --version`.
Design + migration: `project/basara/ARCHITECTURE.md`. Usage: `project/basara/README.md`.

## Hard rules

1. **Never parse or write game formats by hand.** Import `basara.arc`, `basara.xet`,
   `basara.msg`, `basara.font`, `basara.markup`, `basara.psl`, `basara.table`.
   If a format feature is missing, add it to `basara` with a test first.
2. **Never write into the live tree with ad-hoc code.** Changes are a patchset TOML →
   `basara build` → `basara install` (verified backup, hash-guarded atomic write,
   read-back, INSTALL_RECORD.json) → `basara rollback` if needed. No ROOT-READY ZIPs.
3. **Text is edited as markup** (`{br}` `{p}` `{end}` `{c:N}…{/c}` `{spk:N}`), never as
   raw words. The FIM contract is re-derived and the whole table re-checked on every build.
4. **Grammar is detected, not assumed** (`basara msg tables <arc>`). UNCHARTED = stop.
5. **Textures are painted in display space** (`basara tex decode`), written only by
   `xet.graft` / patchset texture ops, bound to the approved candidate's SHA-256.
6. Unknown is fine during engineering and never a release PASS. Cold boot is the final gate.

## Common commands

| Task | Command |
|---|---|
| list an archive (fast, lazy) | `basara arc ls X.arc` |
| message tables + grammar + contract | `basara msg tables X.arc` |
| read records as markup + widths | `basara msg show X.arc id_brief_r -r 1464` |
| whole-tree text health | `basara msg census <rom/eng> --out msg_census.json` |
| whole-tree texture health | `basara tex census <rom/eng> --ref <rom/jpn> --out xet_census.json` |
| translator round trip | `basara catalog export / lint / import` |
| build / install / rollback | `basara build P.toml --root R --out B` · `basara install B --root R --backup-root K` · `basara rollback K/<id>/INSTALL_RECORD.json` |
