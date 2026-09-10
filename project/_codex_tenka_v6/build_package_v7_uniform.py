from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zipfile

import build_package_v7 as base


STAGE_SCALE = 0.52
original_build_tenka = base.build_tenka
original_build_package = base.build_package


def patch_layout_uniform(raw: bytes):
    if raw[:4] != b"\0PSL" or len(raw) != 66296:
        raise AssertionError("unexpected tenka_00 layout")
    output = bytearray(raw)
    records = []
    expected_changed = set()
    for row, node in enumerate(base.STAGE_NODES):
        record = 16 + node * 176
        x_offset = record + 0x20
        y_offset = record + 0x24
        before_x = struct.unpack_from(">f", raw, x_offset)[0]
        before_y = struct.unpack_from(">f", raw, y_offset)[0]
        geometry = [struct.unpack_from(">i", raw, record + offset)[0] for offset in (0x74, 0x78, 0x7C, 0x80)]
        if not (abs(before_x - 0.54) < 1e-6 and abs(before_y - 0.88) < 1e-6):
            raise AssertionError({"node": node, "scale": [before_x, before_y]})
        if geometry != [-32, -16, 32, 16]:
            raise AssertionError({"node": node, "geometry": geometry})
        struct.pack_into(">f", output, x_offset, STAGE_SCALE)
        struct.pack_into(">f", output, y_offset, STAGE_SCALE)
        for offset in (x_offset, y_offset):
            for byte in range(4):
                if raw[offset + byte] != output[offset + byte]:
                    expected_changed.add(offset + byte)
        records.append({
            "node": node,
            "parent_row": f"7_0_{row}",
            "scale_x": {"before": before_x, "after": STAGE_SCALE},
            "scale_y": {"before": before_y, "after": STAGE_SCALE},
            "effective_uniform_ratio_from_retail_0_88": STAGE_SCALE / 0.88,
            "geometry": {"before": geometry, "after": geometry, "unchanged": True},
        })
    result = bytes(output)
    actual = base.changed_offsets(raw, result)
    if actual != sorted(expected_changed):
        raise AssertionError({"actual": actual, "expected": sorted(expected_changed)})
    return result, records, actual


def build_tenka_uniform(path):
    output_path, report = original_build_tenka(path)
    report["method"] = "uniform dynamic-text scale: X/Y 0.52 on seven reusable St_s list slots"
    report["evidence"].pop("geometry", None)
    report["evidence"]["dynamic_scale"] = (
        "All untouched dummy_BM text nodes use equal X/Y values. V6 changed X only and runtime pixels "
        "remained identical, so V7 supplies the list renderer a uniform 0.52 text scale."
    )
    report["predicted_runtime"] = {
        "retail_scale": 0.88,
        "v7_scale": STAGE_SCALE,
        "ratio": STAGE_SCALE / 0.88,
        "longest_observed_width_px": 738,
        "predicted_longest_width_px": round(738 * STAGE_SCALE / 0.88, 1),
        "measured_row_interior_px": 438,
    }
    (base.ROOT / "V7_TENKA_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path, report


README = """Sengoku BASARA 3 Utage English Patch - Free Battle Dynamic Bounds V7

This is cumulative over V6. Merge PS3_GAME into the extracted game root and overwrite.

V6 runtime results:
- Quick Battles works.
- The counter suffix Battles works.
- The earlier horizontal-only St_s X edit did not affect dynamic stage text and is superseded here.

V7 changes only id\\lsp\\jpn\\tenka\\tenka_00 inside rom/eng/tenka/tenka_id.arc. The seven reusable St_s list templates now use a uniform 0.52 X/Y scale. V6 changed only X while Y stayed at 0.88, and the dynamic text renderer preserved the old size. Setting both components together uses the renderer's uniform text-size path. The seven slots render all 38 stage names, so the correction applies universally across the scrolling list.

The 0.52 value is 59.1% of retail 0.88. Applied to the measured 738-pixel longest title, it predicts about 436 pixels against a roughly 438-pixel row interior. Text height also scales down and must be checked for readability in engine.

GSM, FIM, TNF, CSA, font atlases, Quick Battles, Battles, geometry, and the right-side selected-stage title are untouched. Offline ARC, resource, byte-scope, ZIP, and checksum validation pass. A cold-boot engine test is still required before runtime confirmation.
"""


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_package_uniform(tenka_path, report):
    package = original_build_package(tenka_path, report)
    (base.RELEASE_DIR / "README_FREE_BATTLE_V7.txt").write_text(README, encoding="utf-8")
    files = sorted(path for path in base.RELEASE_DIR.rglob("*") if path.is_file())
    with zipfile.ZipFile(base.OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, path.relative_to(base.RELEASE_DIR).as_posix())
    with zipfile.ZipFile(base.OUTPUT_ZIP) as output:
        if output.testzip() is not None or len(output.namelist()) != len(files):
            raise AssertionError("uniform V7 ZIP integrity failure")
    output_hash = sha256_file(base.OUTPUT_ZIP)
    base.OUTPUT_SHA.write_text(f"{output_hash}  {base.OUTPUT_ZIP.name}\n", encoding="ascii")
    shutil.copy2(base.OUTPUT_ZIP, base.DOWNLOAD_ZIP)
    shutil.copy2(base.OUTPUT_SHA, base.DOWNLOAD_SHA)
    package["zip_sha256"] = output_hash
    package["zip_file_count"] = len(files)
    return package


if __name__ == "__main__":
    base.patch_layout = patch_layout_uniform
    base.build_tenka = build_tenka_uniform
    base.build_package = build_package_uniform
    base.main()
