from __future__ import annotations
import sys, io
from pathlib import Path
sys.path.insert(0, r"e:/Utage Patching New/_codex_tenka_v6")
import arc_tools as arc
from build_free_battle_v6 import xet_info, dds_header

ROOT = Path(r"e:/Utage Patching New")
ARC = ROOT / "PS3_GAME/USRDIR/nativePS3/rom/eng/title.arc"
OUT = ROOT / "_codex_tenka_v6/_title_extract"
OUT.mkdir(parents=True, exist_ok=True)

def decode(raw):
    i = xet_info(raw)
    data = raw[i["texture_offset"]:i["texture_offset"]+i["payload_size"]]
    return Image.open(io.BytesIO(dds_header(i["width"],i["height"],i["payload_size"],i["fourcc"])+data)).convert("RGBA")

from PIL import Image

a = arc.parse_arc(ARC)
# Candidates: title_000-017, title2_000-003, id_title_00-05
want_indices = []
want_named = []
for e in a.entries:
    n = e.name.lower()
    if "\\title\\" in n or "\\title2\\" in n or "id_title_" in n:
        if e.type_hash == 0x241F5DEB:
            want_indices.append(e.index)

# Contact sheet
tiles = []
for idx in want_indices:
    e = a.entries[idx]
    raw = arc.unpack(e)
    im = decode(raw)
    tag = e.name.split("\\")[-1].replace("_ID_HQ","")
    fp = OUT / f"{tag}.png"
    im.save(fp)
    tiles.append((idx, tag, im, fp))
    print(f"{idx:4d} {e.name}  {im.size}  -> {fp.name}")

cols = 4
tw, th = 520, 520
rows = (len(tiles)+cols-1)//cols
sheet = Image.new("RGB", (cols*tw, rows*th), (30,30,34))
from PIL import ImageDraw
d = ImageDraw.Draw(sheet)
for j,(idx,tag,im,fp) in enumerate(tiles):
    scale = min((tw-40)/im.width, (th-60)/im.height, 1.0)
    im2 = im.resize((max(1,int(im.width*scale)), max(1,int(im.height*scale))))
    x = (j%cols)*tw + (tw-im2.width)//2
    y = (j//cols)*th + 40
    sheet.paste(im2, (x,y))
    d.text(((j%cols)*tw+8,(j//cols)*th+8), f"{idx}: {tag}", fill=(255,225,90))
sheet.save(OUT/"CONTACT.png")
print("saved", OUT/"CONTACT.png", "tiles", len(tiles))
