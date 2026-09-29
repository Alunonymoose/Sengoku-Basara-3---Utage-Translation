#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks: list[tuple[bool,str]] = []

def read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        checks.append((False, f"missing required file: {rel}"))
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")

def require(rel: str, needle: str) -> None:
    checks.append((needle in read(rel), f"{rel}: required marker missing: {needle}"))

def forbid(rel: str, needle: str) -> None:
    checks.append((needle not in read(rel), f"{rel}: forbidden stale marker present: {needle}"))

# Runtime-proven texture order must not regress in active code/canon.
forbid("project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetCodec.cs", "SwapColourEndpointEndianInPlace")
forbid("project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetCodec.cs", "colour endpoints as big-endian")
require("project/Foundry/src/BasaraFoundry.Game.Utage/Xet/UtageXetCodec.cs", "standard DXT block byte order")
require("project/Foundry/docs/PUBLIC_TECHNICAL_CANON.md", "standard DXT")
require(".agents/skills/basara-utage-texture-engineering/SKILL.md", "standard DXT")
require("public-plugin/skills/basara-utage-core/references/PUBLIC_TECHNICAL_CANON.md", "standard DXT")

# Runtime-proven Python decoder/writer must be durable and release tooling must use it.
require("project/texture_tools/xet_ps3_2026-09-25/xet_ps3.py", "NO PS3 byte swap")
require("project/tools/release_audit_2026-09-24/texture_review_export.py", "xet_ps3_2026-09-25")
require("project/tools/release_audit_2026-09-24/foundry_release_audit.py", "xet_ps3_2026-09-25")
forbid("project/tools/release_audit_2026-09-24/texture_review_export.py", "foundry_xet_decoder_20260923")
forbid("project/tools/release_audit_2026-09-24/foundry_release_audit.py", "foundry_xet_decoder_20260923")

# Project-state/current live policy must be visible.
for rel in [
    "project/Foundry/docs/PROJECT_CONTROL.md",
    ".agents/skills/basara-project-state/SKILL.md",
    "public-plugin/skills/basara-project-state/SKILL.md",
]:
    require(rel, "snapshot")
    require(rel, "live")

# Active front doors must not route new agents to the obsolete initial branch.
for rel in [
    "README.md",
    "project/Foundry/README.md",
    "project/Foundry/docs/GPT_READ_ME_FIRST.md",
    ".agents/skills/README.md",
    ".agents/skills/basara-utage-core/SKILL.md",
    "public-plugin/skills/basara-utage-core/SKILL.md",
]:
    forbid(rel, "foundry-v0.1")

# Current delivery is live-install by default, not old package-only workflow.
forbid("CLAUDE.md", "Default final delivery is one ROOT-READY ZIP")
forbid(".claude/skills/basara-arc-engineering/SKILL.md", "normally ends in one installation-ready ROOT-READY ZIP")

failed = [msg for ok,msg in checks if not ok]
if failed:
    print("OPERATIONAL CANON GUARD FAILED")
    for msg in failed:
        print(" -", msg)
    raise SystemExit(1)

print(f"Operational canon guard passed ({len(checks)} assertions).")
