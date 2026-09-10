"""Does the LSP layout store the sprite rectangles we are guessing at?

Segmentation found cards at x=2/114/226, y=4, 108x176 on roulette_000.
If those numbers appear in the layout resource, the layout is the answer and
pixel guessing can be thrown away.
"""
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import alrummi3_core as c

ROM = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")
arc = c.parse_arc(ROM / "jpn" / "id" / "cockpit1P.arc")

print("non-texture resources in this archive:")
for e in arc.entries:
    raw = c.unpack_entry(e)
    magic = raw[:4]
    if magic == b"\0XET":
        continue
    print(f"  entry {e.index:3d}  magic {magic!r:12s} {len(raw):8d} bytes  "
          f"0x{e.type_hash:08X}  {e.name[:52]}")

# Look for the layout resources and hunt for our known coordinates.
targets = [2, 114, 226, 108, 176, 512, 256]
for e in arc.entries:
    raw = c.unpack_entry(e)
    if raw[:4] == b"\0XET":
        continue
    name = e.name.lower()
    if "lsp" not in name and raw[:4] not in (b"\0PSL", b"LSP\0", b"\0LSP"):
        continue
    print(f"\n=== {e.name}  magic {raw[:4]!r}  {len(raw)} bytes ===")
    print("  header:", raw[:48].hex())

    # counts of our target values as u16/u32, both endians
    for label, fmt, size in (("u16 BE", ">H", 2), ("u16 LE", "<H", 2),
                             ("u32 BE", ">I", 4), ("u32 LE", "<I", 4)):
        hits = {t: [] for t in targets}
        for off in range(0, len(raw) - size, 2):
            value = struct.unpack_from(fmt, raw, off)[0]
            if value in hits:
                hits[value].append(off)
        summary = {t: len(v) for t, v in hits.items() if v}
        if summary:
            print(f"  {label}: {summary}")

    # float coordinates are just as likely
    for label, fmt in (("f32 BE", ">f"), ("f32 LE", "<f")):
        found = []
        for off in range(0, len(raw) - 4, 4):
            value = struct.unpack_from(fmt, raw, off)[0]
            if value in (2.0, 114.0, 226.0, 108.0, 176.0, 512.0, 256.0):
                found.append((off, value))
        if found:
            print(f"  {label}: {len(found)} matches, first 12 -> {found[:12]}")
