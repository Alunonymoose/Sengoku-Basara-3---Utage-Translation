import importlib.util
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "ascii_csa.py"
spec = importlib.util.spec_from_file_location("ascii_csa", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_csa_roundtrip():
    mapping = [0xFFFF] * 128
    mapping[0x20] = 0
    mapping[0x41] = 32
    blob = mod.encode_csa(100, mapping)
    got = mod.parse_csa(blob)
    assert got["header_field"] == 100
    assert got["mapping"] == mapping
    assert len(blob) == 264


def test_dominant_ascii_shape():
    mapping = [0xFFFF] * 128
    glyph = 0
    for code in range(0x20, 0x80):
        if code == 0x26:
            continue
        mapping[code] = glyph
        glyph += 1
    assert glyph == 95
    assert mapping[0x20] == 0
    assert mapping[0x26] == 0xFFFF
    assert mapping[0x27] == 6
    assert mapping[0x7F] == 94
