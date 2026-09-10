"""Re-extract project_data from the translation workset.

`project_data/` is a *derived copy*. The master handover document is explicit
that `utage_translation_workset.zip` — the 14,948-entry dictionary and the
glyph consensus — is the irreplaceable source of truth, and that it is
refreshed as work lands. Run this after any refresh so Alrummi 3 is not
translating against a stale dictionary.

    python refresh_project_data.py [path\\to\\utage_translation_workset.zip]
"""

from __future__ import annotations

import gzip
import json
import pickle
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_WORKSET = Path(r"E:\Utage Patching New\utage_translation_workset.zip")

WANTED = {
    "workset/work/dict_pl029.json": "utage_dictionary.json",
    "workset/work/names.py": "names.py",
    "workset/work/tr/singles.py": "singles.py",
}


def main() -> int:
    workset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKSET
    if not workset.is_file():
        print(f"workset not found: {workset}")
        return 1
    out = HERE / "project_data"
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(workset) as archive:
        names = set(archive.namelist())
        for source, target in WANTED.items():
            if source not in names:
                print(f"  missing from workset, skipped: {source}")
                continue
            raw = archive.read(source)
            if target.endswith(".json"):
                data = json.loads(raw)
                (out / target).write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
                print(f"  {target}: {len(data)} entries")
            else:
                (out / target).write_bytes(raw)
                print(f"  {target}: {len(raw)} bytes")

    # The per-archive glyph maps decode Japanese dialogue.  They are 30
    # separate pickles in the workset and 20 MB merged, so they are stored
    # here as one gzipped index instead.
    merged: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(workset) as archive:
        for name in archive.namelist():
            if "glyph_maps_pl" not in name:
                continue
            try:
                maps = pickle.loads(archive.read(name))
            except Exception as exc:
                print(f"  glyph map {name} could not be read: {exc}")
                continue
            for arc_name, mapping in maps.items():
                merged.setdefault(arc_name, {}).update(
                    {str(k): v for k, v in mapping.items()}
                )
    if merged:
        target = out / "glyph_maps.json.gz"
        with gzip.open(target, "wt", encoding="utf-8", compresslevel=9) as stream:
            json.dump(merged, stream, ensure_ascii=False)
        size = target.stat().st_size / 1024 / 1024
        print(f"  glyph_maps.json.gz: {len(merged)} archives, {size:.2f} MB")

    print(f"project_data refreshed from {workset}")
    print("Rebuild the EXE, or copy project_data/ beside it, to pick this up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
