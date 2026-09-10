"""Small dependency-light preflight for every Alrummi 3 V4.1 build."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
from PIL import Image

import alrummi3_v4 as v4
import alrummi3_v41  # noqa: F401 - import itself is a regression check
import v4_mttex_codec as codec
import v41_donor_validate as gate
import v41_image_edit


def _image(value: int) -> Image.Image:
    arr = np.zeros((32, 32, 4), dtype=np.uint8)
    arr[..., :3] = value
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


class FakeOCR:
    def __init__(self, text: str):
        self.text = text
    def read_regions(self, _image, scale=3):
        return [SimpleNamespace(text=self.text, box=(4, 8, 28, 24), confidence=0.99)]


def test_codec_transform():
    samples = np.array([[[
        255, 0, 0, 255
    ], [0, 255, 0, 200], [0, 0, 255, 128], [128, 128, 128, 64], [17, 200, 99, 0]]], dtype=np.uint8)
    stored = codec.display_to_storage(samples, 0x2A)
    back = codec.storage_to_display(stored, 0x2A)
    error = np.max(np.abs(back.astype(np.int16) - samples.astype(np.int16)))
    assert error <= 1, f"MT YCbCr inverse error is {error} LSB"


def test_identical_donor_rejected():
    source = _image(30)
    verdict = gate.validate_donor(
        source, b"same", source.copy(), b"same",
        r"E:\SAMURAI HEROES\rom\eng\id\cockpit.arc",
        ocr_engine=FakeOCR("PLAY"), source_ocr="対戦",
    )
    assert not verdict.accepted
    assert any("identical" in reason for reason in verdict.reasons)


def test_still_japanese_donor_rejected():
    verdict = gate.validate_donor(
        _image(20), b"source", _image(80), b"donor",
        r"E:\SAMURAI HEROES\rom\eng\id\cockpit.arc",
        ocr_engine=FakeOCR("対戦"), source_ocr="対戦",
    )
    assert not verdict.accepted
    assert verdict.donor_japanese


def test_explicit_jpn_provider_rejected():
    verdict = gate.validate_donor(
        _image(20), b"source", _image(80), b"donor",
        r"E:\SAMURAI HEROES\rom\jpn\id\cockpit.arc",
        ocr_engine=FakeOCR("PLAY"), source_ocr="対戦",
    )
    assert not verdict.accepted
    assert any("/jpn/" in reason for reason in verdict.reasons)


def test_proven_english_donor_accepted():
    verdict = gate.validate_donor(
        _image(20), b"source", _image(80), b"donor",
        r"E:\SAMURAI HEROES\rom\eng\id\cockpit.arc",
        ocr_engine=FakeOCR("PLAY"), source_ocr="対戦",
    )
    # Non-XET synthetic data cannot earn exact-layout points, but explicit
    # English provenance + visible change + Latin OCR + Japanese removed is
    # deliberately enough.
    assert verdict.accepted, verdict.reasons


def test_edit_boxes_merge():
    edits = [
        v41_image_edit.TextEdit(v4.core.Region(10, 10, 30, 20), "大吉", "GREAT LUCK"),
        v41_image_edit.TextEdit(v4.core.Region(32, 10, 45, 20), "吉", "GOOD LUCK"),
    ]
    boxes = v41_image_edit.merged_edit_boxes(edits, (128, 64))
    assert boxes
    for box in boxes:
        assert 0 <= box.left < box.right <= 128
        assert 0 <= box.top < box.bottom <= 64


def test_apply_path_keeps_existing_safety_guards():
    source = inspect.getsource(v4.AlrummiV4App._v4_apply_worker)
    assert "core.sha256(disk_raw) != core.sha256(self.source_raw)" in source
    assert "core.verify_single_replacement" in source
    assert ".alrummi-original.bak" in source
    assert ".alrummi-previous.bak" in source


def main():
    tests = [
        test_codec_transform,
        test_identical_donor_rejected,
        test_still_japanese_donor_rejected,
        test_explicit_jpn_provider_rejected,
        test_proven_english_donor_accepted,
        test_edit_boxes_merge,
        test_apply_path_keeps_existing_safety_guards,
    ]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"V4.1 preflight: {len(tests)} tests passed")


if __name__ == "__main__":
    main()
