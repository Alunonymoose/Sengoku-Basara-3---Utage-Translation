# AI Portability and Fresh-Account Bootstrap

The project should remain useful even when the original ChatGPT memory, private plugin or connected Drive is unavailable.

## Minimum bootstrap for another researcher

A new researcher can begin with:

1. this public repository/branch;
2. the documents in `project/Foundry/docs`;
3. the reusable skills in `.agents/skills`;
4. their own legally obtained Utage / Samurai Heroes files as required by the task.

The model should be told to treat the repository as reusable technical canon and the researcher's fresh local files as production authority.

## Suggested fresh-session instruction

```text
You are continuing/reproducing BASARA Foundry work for Sengoku BASARA 3 Utage.

Read the public Foundry Core documentation and .agents/skills in this repository before making technical assumptions.
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

1. public technical canon;
2. public skills;
3. current code/tests;
4. public checkpoints/research notes relevant to the exact subsystem;
5. fresh local game bytes;
6. only then external/general MT Framework knowledge.

Do not recreate months of architecture research if the repository already contains the proof.


## Portable plugin source

A clean public plugin source is maintained in `public-plugin/`. It mirrors the reusable public skills and canon without bundling retail game payloads.

Another account can package that directory and import it where the platform supports private plugin creation. Even without plugin support, the same skills are plain Markdown and can be supplied directly to another model.
