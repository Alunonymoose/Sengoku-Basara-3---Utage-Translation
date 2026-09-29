# AI Portability and Fresh-Account Bootstrap

The project should remain useful even when the original ChatGPT memory, private plugin or connected Drive is unavailable.

## Minimum bootstrap for another researcher

A new researcher can begin with:

1. this public repository/branch;
2. `project/Foundry/docs/PROJECT_CONTROL.md`;
3. the relevant documents in `project/Foundry/docs`;
4. the reusable skills in `.agents/skills`, especially `basara-project-state`;
5. their own legally obtained Utage / Samurai Heroes files as required by the task.

The model should be told to treat the repository as reusable technical canon and the researcher's fresh local files as production authority.

## Suggested fresh-session instruction

```text
You are continuing/reproducing BASARA Foundry work for Sengoku BASARA 3 Utage.

Read `project/Foundry/docs/PROJECT_CONTROL.md` and the `basara-project-state` skill first. If my workspace provides `.foundry/PROJECT_CURRENT.json`, read it before making current-state claims. Then read only the relevant current Foundry documentation and domain skill.
Use current repository code/tests as implementation evidence.
Use my fresh game files as the only production mutation source.
Do not ask me to redistribute retail game assets into the repository.
For texture work: decode the real live resource first, prove the editable region, create the exact source-preserving candidate, derive previews from that candidate, approval-gate new art, then encode/rebuild/re-extract/re-decode.
Do not treat containment as runtime ownership or a mockup as a production asset.
Label evidence conservatively and preserve disproven assumptions.
```

This prompt is deliberately short because the durable detail belongs in the repository, not in one giant conversation prompt.

## Model independence

The same material can be supplied to ChatGPT, Codex, Claude, DeepSeek, Grok or a human engineer. Models may differ in tool use, but the production states and evidence rules should remain the same.

## ChatGPT plugin relationship

The maintainer may use a private BASARA Foundry ChatGPT plugin for convenience. That plugin is **not** the sole source of truth.

Whenever the plugin gains a durable new rule, a public-safe equivalent should be promoted into this repository. That prevents another account from needing access to the maintainer's private memory or plugin.

## What cannot be portable through the public repo

Do not publish:

- retail ARC/TEX/XET/MSG/EBOOT files;
- extracted Samurai Heroes or Utage artwork;
- disc images;
- copyrighted audio/video;
- private account data or connected-drive secrets.

Instead publish parsers, transforms, hashes, offsets, schemas, test methodology and synthetic fixtures where possible.

## Reconstructing context

When a new researcher lacks a private checkpoint, recover context in this order:

1. `PROJECT_CONTROL.md` and, when present locally, `.foundry/PROJECT_CURRENT.json`;
2. fresh exact target game bytes;
3. the relevant public project-state/domain skills and technical canon;
4. current code/tests;
5. runtime evidence and public checkpoints relevant to the exact subsystem;
6. only then historical notes or external/general MT Framework knowledge.

A dirty snapshot is navigation, not current whole-tree authority. Broad historical search is escalation, not bootstrap.

Do not recreate months of architecture research if the repository already contains the proof.


## Portable plugin source

A clean public plugin source is maintained in `public-plugin/`. It mirrors the reusable public skills and canon without bundling retail game payloads.

Another account can package that directory and import it where the platform supports private plugin creation. Even without plugin support, the same skills are plain Markdown and can be supplied directly to another model.
