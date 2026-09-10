from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, r"e:/Utage Patching New/_codex_tenka_v6")
import arc_tools as arc

ROOT = Path(r"e:/Utage Patching New")
ARCS = [
    "PS3_GAME/USRDIR/nativePS3/rom/eng/title.arc",
    "PS3_GAME/USRDIR/nativePS3/rom/eng/startup.arc",
    "PS3_GAME/USRDIR/nativePS3/rom/eng/title_id.arc",
    "PS3_GAME/USRDIR/nativePS3/rom/eng/title/background.arc",
]
lines = []
for rel in ARCS:
    p = ROOT / rel
    if not p.exists():
        lines.append(f"MISSING {rel}")
        continue
    a = arc.parse_arc(p)
    lines.append(f"== {rel}  entries={len(a.entries)}  endian={a.endian} version={a.version}")
    for e in a.entries:
        lines.append(f"  [{e.index:4d}] {e.name}  type=0x{e.type_hash:08X} comp={e.compressed_size} raw={e.raw_size}")

OUT = Path(r"e:/Utage Patching New/_codex_tenka_v6/_probe_title_report.txt")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {OUT} ({len(lines)} lines)")
