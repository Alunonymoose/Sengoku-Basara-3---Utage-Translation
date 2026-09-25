"""basara.arc: differential proof against the pinned safe_arc, plus lenient/lazy behaviour."""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from basara import arc
from basara.mthash import R_TEXTURE, mt_hash

SAFE_ARC = Path(__file__).resolve().parents[2] / "tools" / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
PIN = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"


def _safe_arc():
    assert hashlib.sha256(SAFE_ARC.read_bytes()).hexdigest() == PIN
    spec = importlib.util.spec_from_file_location("safe_arc_oracle", SAFE_ARC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["safe_arc_oracle"] = mod
    spec.loader.exec_module(mod)
    return mod


SA = _safe_arc()


def test_mt_hash_known_texture_class():
    assert mt_hash("rTexture") == R_TEXTURE == 0x241F5DEB


members_st = st.lists(
    st.tuples(st.text("abcdefgh\\_0123", min_size=1, max_size=40),
              st.integers(0, 0x7FFFFFFF),
              st.binary(min_size=0, max_size=300),
              st.booleans()),
    min_size=1, max_size=6)


def _build(members, alignment):
    # raw members get a 0xFF lead byte so they can never look like a zlib header
    return arc.build([(n, h, d if c else b"\xff" + d, c) for n, h, d, c in members], alignment=alignment)


@settings(max_examples=150, deadline=None)
@given(members=members_st, alignment=st.sampled_from([4, 16, 2048]), data=st.data())
def test_rebuild_is_byte_identical_to_safe_arc(members, alignment, data):
    src = _build(members, alignment)
    n = len(members)
    idx = data.draw(st.sets(st.integers(0, n - 1), max_size=n))
    repl = {i: b"\xff" + data.draw(st.binary(max_size=400)) for i in idx}
    ours = arc.rebuild(src, repl)
    theirs = SA.rebuild_arc(src, repl)
    assert ours == theirs
    a, b = arc.verify_rebuild(src, ours, repl), SA.verify_rebuild(src, theirs, repl)
    assert a["changed_member_count"] == b["changed_member_count"]
    assert [c["after_raw_sha256"] for c in a["changes"]] == [c["after_raw_sha256"] for c in b["changes"]]


@settings(max_examples=60, deadline=None)
@given(members=members_st)
def test_parse_matches_safe_arc(members):
    src = _build(members, 16)
    ours, theirs = arc.read(src), SA.parse_arc(src)
    assert [(e.index, e.name, e.type_hash, e.raw, e.codec, e.packed_size) for e in ours] == \
           [(e["index"], e["name"], e["type_hash"], e["raw"], e["codec"], e["packed_size"]) for e in theirs]


def test_noop_rebuild_returns_identical_bytes():
    src = arc.build([("a", 1, b"x" * 50), ("b", 2, b"y" * 10)])
    assert arc.rebuild(src, {}) == src
    assert arc.rebuild(src, {0: b"x" * 50}) == src


def test_lenient_inspect_reads_special_archives_but_refuses_mutation():
    src = arc.build([("a", 1, b"hello" * 20)]) + b"\x01\x02"
    with pytest.raises(arc.ArcError, match="trailer"):
        arc.read(src)
    ins = arc.inspect(src)
    assert not ins.strict and ins.anomalies and ins[0].raw == b"hello" * 20
    with pytest.raises(arc.ArcError, match="refusing to mutate"):
        ins.rebuild({0: b"x"})
    with pytest.raises(ValueError, match="trailer"):
        SA.parse_arc(src)  # same verdict as the legacy oracle


def test_lazy_magic_does_not_need_full_inflate():
    big = b"\x00GSM" + bytes(2_000_000)
    fresh = arc.inspect(arc.build([("t", 1, big)]))[0]
    assert fresh.magic == b"\x00GSM" and "_decoded" not in fresh.__dict__


def test_find_by_name_suffix_and_magic():
    a = arc.read(arc.build([(r"id\msg\jpn\id_brief_r", 1, b"\x00GSM" + bytes(12)),
                            (r"id\msg\jpn\id_brief_r", 2, b"\x00FIM" + bytes(28)),
                            (r"id\msg\jpn\id_brief", 3, b"\x00GSM" + bytes(12))]))
    assert a.find("id_brief_r", magic=b"\x00FIM").index == 1
    assert a.pair(a[0], b"\x00FIM").index == 1
    with pytest.raises(arc.ArcError, match="matched 2"):
        a.find("id_brief_r")


def test_declared_size_warning_member_refuses_length_change():
    raw = b"z" * 64
    src = bytearray(arc.build([("w", 1, raw)]))
    # corrupt the declared size (packed_size) the way real cockpit1P dummy_BM does
    import struct
    struct.pack_into(">I", src, 8 + 72, (70 << 3))
    src = bytes(src)
    a = arc.read(src)
    assert a[0].warning
    with pytest.raises(arc.ArcError, match="declared-size"):
        arc.rebuild(src, {0: b"q" * 10})
    assert arc.read(arc.rebuild(src, {0: b"q" * 64}))[0].packed_size == 70 << 3
