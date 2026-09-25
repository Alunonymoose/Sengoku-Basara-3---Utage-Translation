"""Regression suite for utage_xet. Run: python -m pytest project/texture_tools/utage_xet -q

The colour-regression tests exist to catch the exact 2026-09-25 menu.arc
failure: a writer that BC3-encodes display RGBA into 0x2A (and/or swaps
endpoint bytes) round-trips through its own decoder but renders
magenta/cyan/green in game. They judge output in DISPLAY space through the
Kuriimu2 shader, independently of any encoder assumption.
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utage_xet as ux  # noqa: E402


def build_xet(w, h, fmt, payload=None, mips=1, swizzle=0):
    bs = 8 if fmt in (0x13, 0x14, 0x19) else 16
    size = ((w + 3) // 4) * ((h + 3) // 4) * bs
    off = 16 + 4 * mips
    raw = bytearray(b"\x00XET")
    raw += struct.pack(">I", 0x97 | (swizzle << 12) | (2 << 28))
    raw += struct.pack(">I", mips | (w << 6) | (h << 19))
    raw += struct.pack(">I", 1 | (fmt << 8))
    raw += struct.pack(">I", off)
    for i in range(1, mips):
        raw += struct.pack(">I", off + size)
    raw += payload if payload is not None else bytes(size)
    for _ in range(1, mips):
        raw += bytes(size)
    return bytes(raw)


def neutral_0x2a(w=32, h=32):
    """Live-like 0x2A: grey plate, white text-ish stripe, transparent border,
    written with the certified writer from an all-zero shell."""
    shell = build_xet(w, h, 0x2A)
    shell = bytes(shell[:20]) + bytes([0, 0] + [0] * 6 + [0xEF, 0x7B, 0xEF, 0x7B] + [0] * 4) * ((w // 4) * (h // 4))
    img = np.zeros((h, w, 4), np.uint8)
    img[4:28, 4:28] = (90, 90, 90, 255)
    img[12:20, 8:24] = (255, 255, 255, 255)
    out, _ = ux.graft(shell, img, allow_inconclusive_byte_order=True)
    return out, img


# ---------------------------------------------------------------- header
def test_header_fields():
    raw = build_xet(64, 32, 0x2A)
    i = ux.xet_info(raw)
    assert (i.width, i.height, i.mip_count, i.format_code, i.version, i.swizzle) == (64, 32, 1, 0x2A, 0x97, 0)
    assert i.codec == "BC3" and i.semantics == "ycbcr"


def test_unknown_format_and_swizzle_fail_closed():
    with pytest.raises(ux.XetError):
        ux.decode_display(build_xet(4, 4, 0x55))
    with pytest.raises(ux.XetError):
        ux.decode_display(build_xet(4, 4, 0x2A, swizzle=1))


# ------------------------------------------------- C# parity fixtures
def test_csharp_fixture_standard_order_ycbcr_red():
    blk = bytearray(16)
    blk[0], blk[1] = 76, 0
    blk[8:12] = bytes([0xEA, 0xF7, 0xE0, 0x07])  # standard LE endpoints
    d = ux.decode_display(build_xet(4, 4, 0x2A, bytes(blk)))
    assert (d[..., 0] >= 235).all() and (d[..., 1] <= 20).all() and (d[..., 2] <= 20).all() and (d[..., 3] >= 235).all()


def test_csharp_fixture_bc2_red_standard_order():
    blk = bytes([0xFF] * 8 + [0x00, 0xF8, 0xE0, 0x07] + [0] * 4)
    d = ux.decode_display(build_xet(4, 4, 0x15, blk))
    assert (d[..., 0] == 255).all() and (d[..., 1] == 0).all() and (d[..., 3] == 255).all()


def test_shader_matches_kuriimu_reference_values():
    disp = np.array([[[255, 0, 0, 255], [255, 255, 255, 128], [0, 0, 0, 0]]], np.uint8)
    st = ux.display_to_storage(disp)
    assert st[0, 0].tolist() == [250, 255, 79, 76]   # Cr, a, Cb, Y  (trunc like C# (int) cast)
    assert st[0, 1].tolist() == [122, 128, 123, 255]  # 122.999.. truncates, same IEEE order as C#
    assert st[0, 2].tolist() == [123, 0, 123, 0]


# ------------------------------------------------ colour regression
PATCHES = {
    "red": (255, 0, 0, 255), "green": (0, 255, 0, 255), "blue": (0, 0, 255, 255),
    "white": (255, 255, 255, 255), "white50": (255, 255, 255, 128), "navy": (0, 56, 132, 255),
}


def _patch_candidate(base_display):
    cand = base_display.copy()
    for k, (name, c) in enumerate(PATCHES.items()):
        y, x = 8 * (k // 3), 8 * (k % 3) + 4
        cand[y:y + 8, x:x + 8] = c
    cand[24:32, 0:8] = (0, 0, 0, 0)  # transparent with black hidden RGB
    return cand


def test_certified_writer_renders_true_colours():
    live, _ = neutral_0x2a()
    base = ux.decode_display(live)
    cand = _patch_candidate(base)
    out, rep = ux.graft(live, cand)
    got = ux.decode_display(out).astype(int)
    for k, (name, c) in enumerate(PATCHES.items()):
        y, x = 8 * (k // 3), 8 * (k % 3) + 4
        err = np.abs(got[y:y + 8, x:x + 8] - np.array(c)).max()
        assert err <= 12, (name, err)
    assert (got[24:32, 0:8, 3] == 0).all()
    assert rep.ok and rep.outside_touched_bytes_identical


def _legacy_xetenc_block(display_block):
    """Faithful behaviour of the quarantined 2026-09-24 xetenc.py: bounding-box
    BC3 of DISPLAY RGBA, colour endpoints written big-endian."""
    px = display_block.reshape(16, 4).astype(int)
    a0, a1 = int(px[:, 3].max()), int(px[:, 3].min())
    q = lambda c: ((c[0] * 31 + 127) // 255) << 11 | ((c[1] * 63 + 127) // 255) << 5 | ((c[2] * 31 + 127) // 255)
    c0, c1 = q(px[:, :3].max(0)), q(px[:, :3].min(0))
    return bytes([a0, a1]) + bytes(6) + struct.pack(">HH", c0, c1) + bytes(4)


def test_legacy_writer_is_detected_as_wrong():
    live, _ = neutral_0x2a()
    cand = _patch_candidate(ux.decode_display(live))
    out = bytearray(live)
    bw = 32 // 4
    for by in range(8):
        for bx in range(8):
            o = 20 + (by * bw + bx) * 16
            out[o:o + 16] = _legacy_xetenc_block(cand[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4])
    got = ux.decode_display(bytes(out)).astype(int)
    white_err = np.abs(got[8:16, 4:12] - np.array(PATCHES["white"])).max()
    assert white_err > 80  # psychedelic in game; the suite must see it
    ev = ux.byte_order_evidence(bytes(out))
    assert ev["verdict"] != "standard" or ev["standard"] < 0.9


# ----------------------------------------------------- graft safety
def test_noop_graft_is_byte_identical():
    live, _ = neutral_0x2a()
    out, rep = ux.graft(live, ux.decode_display(live))
    assert out == live and rep.blocks_touched == 0


def test_only_changed_blocks_are_rewritten():
    live, _ = neutral_0x2a()
    cand = ux.decode_display(live).copy()
    cand[5, 5] = (10, 200, 30, 255)
    out, rep = ux.graft(live, cand)
    assert rep.touched_blocks == [(1, 1)]
    diff = [i for i in range(len(live)) if live[i] != out[i]]
    blk = 20 + (1 * 8 + 1) * 16
    assert diff and all(blk <= i < blk + 16 for i in diff)


def test_edit_outside_mask_refused():
    live, _ = neutral_0x2a()
    cand = ux.decode_display(live).copy()
    cand[0, 0] = (1, 2, 3, 255)
    mask = np.zeros((32, 32), bool)
    mask[16:, 16:] = True
    with pytest.raises(ux.XetError):
        ux.graft(live, cand, mask=mask)


def test_swapped_target_refused():
    live, _ = neutral_0x2a()
    sw = bytearray(live)
    for o in range(20, len(sw), 16):
        sw[o + 8], sw[o + 9], sw[o + 10], sw[o + 11] = sw[o + 9], sw[o + 8], sw[o + 11], sw[o + 10]
    assert ux.byte_order_evidence(live)["verdict"] == "standard"
    assert ux.byte_order_evidence(bytes(sw))["verdict"] == "swapped"
    with pytest.raises(ux.XetError):
        ux.graft(bytes(sw), ux.decode_display(bytes(sw)))


@pytest.mark.parametrize("fmt", [0x15, 0x19, 0x2B, 0x27])
def test_uncertified_formats_refuse_write(fmt):
    raw = build_xet(4, 4, fmt) if fmt != 0x27 else build_xet(4, 4, 0x27, bytes(64))
    with pytest.raises(ux.XetError):
        ux.graft(raw, np.zeros((4, 4, 4), np.uint8), allow_inconclusive_byte_order=True)


def test_multimip_refused():
    with pytest.raises(ux.XetError):
        ux.graft(build_xet(8, 8, 0x2A, mips=2), np.zeros((8, 8, 4), np.uint8),
                 allow_inconclusive_byte_order=True)


def test_encoder_always_emits_four_colour_blocks():
    rng = np.random.default_rng(1)
    for _ in range(200):
        blk = rng.integers(0, 256, (4, 4, 4), dtype=np.uint8)
        if rng.random() < 0.3:
            blk[:] = blk[0, 0]
        b = ux.encode_bc3_block(blk)
        c0, c1 = struct.unpack_from("<HH", b, 8)
        assert c0 > c1


def test_plain_bc3_graft_roundtrip_0x17():
    live = build_xet(16, 16, 0x17, bytes([255, 255] + [0] * 6 + [0xFF, 0xFF, 0, 0] + [0] * 4) * 16)
    cand = ux.decode_display(live).copy()
    cand[4:8, 4:8] = (200, 40, 40, 255)
    out, rep = ux.graft(live, cand)
    got = ux.decode_display(out)
    assert np.abs(got[4:8, 4:8].astype(int) - [200, 40, 40, 255]).max() <= 8
    assert rep.blocks_touched == 1


def test_prefill_dilate_fills_hidden_rgb():
    img = np.zeros((8, 8, 4), np.uint8)
    img[:4, :4] = (0, 0, 255, 255)
    out = ux.prefill_transparent_rgb(img, "dilate")
    assert (out[..., 3] == img[..., 3]).all()
    assert tuple(out[7, 7, :3]) == (0, 0, 255)


def test_scan_flags_legacy_edit_against_reference():
    ref, _ = neutral_0x2a()
    base = ux.decode_display(ref)
    cand = base.copy()
    cand[4:12, 4:28] = (255, 255, 255, 255)   # new English lettering in the sheet's own colours
    cand[6:10, 8:24] = (90, 90, 90, 255)
    bad = bytearray(ref)
    for by in range(1, 3):
        for bx in range(1, 7):
            o = 20 + (by * 8 + bx) * 16
            bad[o:o + 16] = _legacy_xetenc_block(cand[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4])
    res = ux.scan_against_reference(bytes(bad), ref)
    assert res["blocks_changed"] > 0 and res["suspect_legacy_encoding"] is True
    good, _ = ux.graft(ref, cand)
    assert ux.scan_against_reference(good, ref)["suspect_legacy_encoding"] is False
    good2, _ = ux.graft(ref, _patch_candidate(base))   # saturated but correct colours
    assert ux.scan_against_reference(good2, ref)["suspect_legacy_encoding"] is False


# ------------------------------------------------ ARC end-to-end (CLI)
def _build_arc(members):
    import zlib
    head = b"\x00CRA" + struct.pack(">HH", 8, len(members))
    table, blobs = b"", b""
    off = 8 + 80 * len(members)
    off = (off + 15) // 16 * 16
    body_start = off
    for name, raw in members:
        stored = zlib.compress(raw, 9)
        pad = (-len(blobs)) % 16
        blobs += b"\0" * pad
        o = body_start + len(blobs)
        table += name.encode().ljust(64, b"\0") + struct.pack(">IIII", 0x241F5DEB, len(stored), (len(raw) << 3) | 4, o)
        blobs += stored
    data = head + table
    return data + b"\0" * (body_start - len(data)) + blobs


def test_arc_graft_end_to_end(tmp_path):
    import xetcli
    live, _ = neutral_0x2a()
    other = b"PSL-untouched" * 40
    arc = _build_arc([(r"id\texture\jpn\menu\menu_058_ID_HQ", live), (r"id\layout\kessen_rule", other)])
    src = tmp_path / "menu.arc"
    src.write_bytes(arc)
    cand = ux.decode_display(live).copy()
    cand[4:12, 4:28] = (255, 255, 255, 255)
    xetcli.write_png(tmp_path / "cand.png", cand)
    out = tmp_path / "menu_out.arc"
    xetcli.main(["arc-graft", str(src), "0", str(tmp_path / "cand.png"), str(out)])
    sa = xetcli.load_safe_arc()
    before, after = sa.parse_arc(arc), sa.parse_arc(out.read_bytes())
    assert after[1]["stored"] == before[1]["stored"]            # protected member byte-identical
    got = ux.decode_display(after[0]["raw"]).astype(int)
    assert np.abs(got[4:12, 4:28] - 255).max() <= 8               # white in DISPLAY space
    rec = json.loads((tmp_path / "menu_out.arc.record.json").read_text())
    assert rec["graft"]["ok"] and rec["arc_verify"]["changed_member_count"] == 1
    census = tmp_path / "c.json"
    xetcli.main(["census", str(tmp_path), "--out", str(census)])
    assert json.loads(census.read_text())["flagged_total"] == 0


def test_release_audit_decoder_matches_canonical_codec():
    """The pinned release-audit decoder and utage_xet must never diverge."""
    import importlib.util
    p = Path(__file__).resolve().parents[1] / "xet_recovery_2026-09-23" / "foundry_xet_decoder_20260923.py"
    spec = importlib.util.spec_from_file_location("fxd", p)
    fxd = importlib.util.module_from_spec(spec)
    sys.modules["fxd"] = fxd
    spec.loader.exec_module(fxd)
    rng = np.random.default_rng(7)
    for fmt in (0x2A, 0x17, 0x15, 0x19):
        bs = 8 if fmt == 0x19 else 16
        raw = build_xet(16, 8, fmt, rng.integers(0, 256, 8 * bs, dtype=np.uint8).tobytes())
        ours = ux.decode_display(raw)
        theirs = np.frombuffer(fxd.decode_rgba(raw, 0), np.uint8).reshape(8, 16, 4)
        assert np.array_equal(ours, theirs), hex(fmt)
