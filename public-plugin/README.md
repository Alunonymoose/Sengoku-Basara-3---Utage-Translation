# BASARA Foundry Core — Portable Plugin Source

This directory is a public, retail-asset-free source package for the reusable BASARA Foundry engineering skills.

It exists so another ChatGPT/Codex account — or another compatible agent system — can start with the project's hard-won methodology without access to the maintainer's private chats, memory, Drive or private plugin.

## Use

If your agent platform supports repository skills directly, point it at the repository's `.agents/skills`.

For systems that accept a plugin archive, package the **contents of this directory** so `plugin.json` is at the archive root.

Unix/macOS:

```sh
zip -r ../BASARA-Foundry-Core-plugin.zip plugin.json .codex-plugin skills
```

PowerShell:

```powershell
Compress-Archive -Path plugin.json,.codex-plugin,skills -DestinationPath ..\BASARA-Foundry-Core-plugin.zip -Force
```

Then import/create a private plugin from that archive where the target platform supports it. Platform publication/listing may require separate platform controls.

Always provide your own lawfully obtained game files for production work. This package contains methodology and public canon, not retail payloads.

## Licence

Plugin/source instructions are CC BY 4.0 unless a software file says otherwise. Project-authored software is MIT licensed. See the repository root licences and `NOTICE.md`.
