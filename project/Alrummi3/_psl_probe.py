"""Crack enough of \0PSL to get the sprite rectangles for one sheet."""
import struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import alrummi3_core as c

ROM = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")
arc = c.parse_arc(ROM / "jpn" / "id" / "cockpit1P.arc")
entry = [e for e in arc.entries if e.name.endswith("roulette")][0]
raw = c.unpack_entry(entry)
print(f"{entry.name}  {len(raw)} bytes")
print("header:", raw[:64].hex())

version = struct.unpack_from(">I", raw, 4)[0]
unk = struct.unpack_from(">I", raw, 8)[0]
a, b = struct.unpack_from(">HH", raw, 12)
print(f"version 0x{version:X}  unk {unk}  countA {a}  countB {b}")

# Where do the names live? Look for readable ASCII runs.
runs = []
current = bytearray()
start = 0
for i, byte in enumerate(raw):
    if 32 <= byte < 127:
        if not current:
            start = i
        current.append(byte)
    else:
        if len(current) >= 4:
            runs.append((start, current.decode("ascii", "replace")))
        current = bytearray()
print(f"\n{len(runs)} ascii runs; first 20:")
for off, text in runs[:20]:
    print(f"  0x{off:05X}  {text[:44]!r}")

# If nodes are fixed size, (name_table_start - body_start) / count is integer.
if runs:
    first_name = runs[0][0]
    body = 16
    span = first_name - body
    print(f"\nbody 0x{body:X}..0x{first_name:X} = {span} bytes")
    for count in (a, b, a + b):
        if count:
            print(f"  / {count:4d} = {span / count:8.2f}")

# Hunt for float rectangles that match what segmentation found.
known = [(2, 4, 108, 176), (114, 4, 108, 176), (226, 22, 108, 158)]
print("\nlooking for the card rectangles as floats or ints…")
for label, fmt, size in ((">f", ">f", 4), ("<f", "<f", 4), (">h", ">h", 2), (">H", ">H", 2)):
    values = []
    for off in range(0, len(raw) - size, size):
        values.append((off, struct.unpack_from(fmt, raw, off)[0]))
    for (x, y, w, h) in known:
        for i in range(len(values) - 3):
            window = [v for _o, v in values[i:i + 4]]
            if all(abs(float(window[k]) - float(t)) < 1.5 for k, t in enumerate((x, y, w, h))):
                print(f"  {label}: {(x,y,w,h)} found at 0x{values[i][0]:05X} -> {window}")
                break
