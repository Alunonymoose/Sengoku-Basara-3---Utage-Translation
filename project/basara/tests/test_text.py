"""Markup round trip, fonts, width measurement, PSL."""
import struct

import pytest
from hypothesis import given, settings, strategies as st

from basara.font import Csa, Tnf, measure
from basara.markup import MarkupError, decode, encode, placeables
from basara.msg import WESTERN
from basara.psl import Psl
from fixtures import csa_blob, tnf_blob

CSA = Csa.parse(csa_blob())
TNF = Tnf.parse(tnf_blob())

control = st.sampled_from([[0xFFFE], [0xFFFD], [0xFFFF], [0xFF91], [0xFC12]]) | \
    st.builds(lambda w, a: [w] + a, st.sampled_from([0xFF92, 0xFC0D, 0xFC0F, 0xFFFA]), st.lists(st.integers(0, 0xFFFF), min_size=1, max_size=1)) | \
    st.builds(lambda a: [0xFC17] + a, st.lists(st.integers(0, 0xFFFF), min_size=3, max_size=3))
plain = st.integers(0, 0xEFFF).map(lambda w: [w])


@settings(max_examples=500, deadline=None)
@given(st.lists(control | plain, max_size=40))
def test_markup_round_trips_every_valid_word_run(chunks):
    words = [w for c in chunks for w in c]
    assert encode(decode(words, CSA), CSA) == words


def test_readable_markup():
    w = encode("Press {c:3}Release{/c} to escape{br}the ambush.{end}", CSA)
    assert w[:6] == [CSA.ordinal("P"), CSA.ordinal("r"), CSA.ordinal("e"), CSA.ordinal("s"), CSA.ordinal("s"), 0]
    assert 0xFF92 in w and 0xFF91 in w and 0xFFFE in w and w[-1] == 0xFFFF
    assert decode(w, CSA) == "Press {c:3}Release{/c} to escape{br}the ambush.{end}"


def test_newline_encodes_as_break_and_braces_escape():
    assert encode("a\nb", CSA) == encode("a{br}b", CSA)
    assert decode(encode("{{x}}", CSA), CSA) == "{{x}}"


def test_characters_outside_the_font_are_rejected():
    with pytest.raises(MarkupError, match="not in this font"):
        encode("Café", CSA)


def test_glyph_without_character_is_shown_as_tag():
    assert decode([4000, 0xFFFF], CSA) == "{g:0FA0}{end}"


def test_placeables_ignore_layout_but_keep_structure():
    a = placeables("{spk:2}Hello{br}there{p}{c:3}x{/c}{end}")
    assert a == ["{spk:2}", "{p}", "{c:3}", "{/c}", "{end}"]
    assert placeables("{spk:2}Hi there{p}{c:3}x{/c}{end}") == a


def test_csa_matches_both_historical_descriptions():
    blob = csa_blob()
    for ch in "Az9":
        cp = ord(ch)
        at8 = struct.unpack_from(">H", blob, 8 + 2 * cp)[0]
        at32 = struct.unpack_from(">H", blob, 32 + 2 * (cp - 12))[0]   # gsm_tools wording
        assert CSA.ordinal(ch) == at8 == at32


def test_width_skips_controls_and_arguments_and_splits_lines():
    w = encode("AB{c:3}C{/c}{br}D{end}", CSA)
    m = measure(w, TNF, WESTERN)
    adv = lambda ch: TNF.glyphs[CSA.ordinal(ch)].advance
    assert m.widths == (adv("A") + adv("B") + adv("C"), adv("D"))
    assert m.lines == 2 and m.unknown_glyphs == 0


def test_psl_nodes_and_rects():
    head = b"\x00PSL" + struct.pack(">IIHH", 0x21, 0, 2, 0)
    rec = bytearray(0xB0)
    struct.pack_into(">2f", rec, 0, 10.0, 20.0)
    struct.pack_into(">I", rec, 0x38, 0xFFFFFFFF)
    struct.pack_into(">I", rec, 0x50, 7)
    struct.pack_into(">4f", rec, 0x74, 0, 0, 256, 32)
    struct.pack_into(">4f", rec, 0x84, 0, 32, 256, 64)
    child = bytearray(rec)
    struct.pack_into(">I", child, 0x38, 0)
    p = Psl.parse(head + bytes(rec) + bytes(child))
    assert p.nodes[0].parent is None and p.children(0)[0].index == 1
    assert p.nodes[0].source.scaled(2).height == 64 and p.nodes[0].dest.width == 256



def test_ycbcr_constants_match_capcom_shader():
    """Constants recovered 2026-09-26 from the game's rShaderPackage
    (nativePS3/sc/PS3/Basara/package.spkg, RSX halfword-swapped floats):
    offset f6f9bef6=-0.482353 (-123/255), 0.34414, 0.71414, 1.772, 1.402."""
    import numpy as np
    from basara import xet
    assert xet.NEUTRAL_CHROMA == 123
    game = {"r_cr": 1.402, "g_cb": 0.34414, "g_cr": 0.71414, "b_cb": 1.772}
    # our decode must agree with the game's float math to well under one level everywhere
    st = np.array([[[r, 255, b, y] for r in range(0, 256, 17) for b in range(0, 256, 17) for y in range(0, 256, 51)]], np.uint8)
    ours = xet.storage_to_display(st).astype(float)
    Y = st[..., 3].astype(float); Cb = st[..., 2] - 123.0; Cr = st[..., 0] - 123.0
    g = np.stack([Y + game["r_cr"] * Cr, Y - game["g_cb"] * Cb - game["g_cr"] * Cr, Y + game["b_cb"] * Cb], -1)
    g = np.clip(g, 0, 255)
    assert np.abs(ours[..., :3] - g).max() < 1.0


def test_cube_map_xet_is_refused_with_a_clear_reason():
    import struct
    import pytest
    from basara import xet
    raw = b"\x00XET" + struct.pack(">III", 0x60000097, 0x2001007, 0x12306) + bytes(200)
    with pytest.raises(xet.XetError, match="6 images"):
        xet.xet_info(raw)
