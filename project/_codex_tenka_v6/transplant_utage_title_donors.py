from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import arc_tools
from build_free_battle_v6 import decode_xet, patch_bc3_rect


ROOT = Path(r"E:\Utage Patching New")
RESULT = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\result"
TITLE = ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng\title.arc"
OUT = ROOT / r"_codex_tenka_v6\utage_title_donor_result"


def title_donors() -> list[bytes]:
    archive = arc_tools.parse_arc(TITLE)
    entries = [
        entry for entry in archive.entries
        if "charasele_02_" in entry.name and "_ID_HQ" in entry.name
        and "_qqq_" not in entry.name and "_lock_" not in entry.name
    ]
    entries.sort(key=lambda entry: int(entry.name.rsplit("_", 3)[1]))
    if len(entries) != 30:
        raise ValueError(f"expected 30 native Utage title donors, found {len(entries)}")
    return [arc_tools.unpack(entry) for entry in entries]


def make_small_name(original: bytes, donor: bytes) -> bytes:
    target = decode_xet(original).convert("RGBA")
    source = decode_xet(donor).convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("donor has no visible lettering")
    left, top, right, bottom = bbox
    margin = 10
    crop = source.crop(
        (max(0, left - margin), max(0, top - margin),
         min(source.width, right + margin), min(source.height, bottom + margin))
    )
    scale = min((target.width - 12) / crop.width, (target.height - 12) / crop.height)
    resized = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.Resampling.LANCZOS,
    )
    rendered = Image.new("RGBA", target.size, (0, 0, 0, 0))
    rendered.alpha_composite(
        resized,
        ((target.width - resized.width) // 2, (target.height - resized.height) // 2),
    )
    return patch_bc3_rect(original, rendered, (0, 0, target.width, target.height))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    donors = title_donors()
    report = {"status": "pass", "donor": str(TITLE), "archives": []}
    for number, donor in enumerate(donors):
        path = RESULT / f"pl{number:03}.arc"
        archive = arc_tools.parse_arc(path)
        original_name = arc_tools.unpack(archive.entries[2])
        replacements = {2: make_small_name(original_name, donor), 4: donor}
        path.write_bytes(arc_tools.rebuild(archive, replacements))
        verified = arc_tools.parse_arc(path)
        for index in (2, 4):
            raw = arc_tools.unpack(verified.entries[index])
            image = decode_xet(raw)
            image.save(OUT / f"pl{number:03}_entry_{index}.png")
        report["archives"].append(
            {"archive": str(path), "changed_entries": [2, 4], "donor_index": number}
        )
    report["preview"] = str(OUT / "contact_sheet.png")
    (OUT / "VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "archives": len(report["archives"])}))


if __name__ == "__main__":
    main()
