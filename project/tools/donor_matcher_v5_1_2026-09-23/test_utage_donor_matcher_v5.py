# test_utage_donor_matcher_v5.py
"""
Test suite for V5. Installs a minimal safe_arc-compatible test double in
sys.modules BEFORE importing the module, so the enrichment path is exercised
with the exact field contract safe_arc provides.

Replace this double with the real safe_arc for production:
    PYTHONPATH=/path/to/foundry pytest test_utage_donor_matcher_v5.py
The module will use the real safe_arc automatically when it is importable.
"""
import sys
import types
import zlib
import struct
import json
import hashlib

import pytest


# --- Install a safe_arc test double only when the real one is absent --------

def _install_safe_arc_double():
    if "safe_arc" in sys.modules:
        return
    try:
        __import__("safe_arc")
        return
    except ImportError:
        pass
    mod = types.ModuleType("safe_arc")

    def parse_arc(arc_bytes):
        if len(arc_bytes) < 8:
            raise ValueError("arc too short")
        if arc_bytes[:4] != b"\0CRA":
            raise ValueError("bad magic")
        version = struct.unpack_from(">H", arc_bytes, 4)[0]
        count = struct.unpack_from(">H", arc_bytes, 6)[0]
        if version != 8:
            raise ValueError(f"bad version {version}")
        entries = []
        for i in range(count):
            base = 8 + i * 0x50
            if base + 0x50 > len(arc_bytes):
                raise ValueError("truncated")
            path_b = arc_bytes[base:base + 64]
            name = path_b.split(b"\0", 1)[0].decode("latin-1")
            th = struct.unpack_from(">I", arc_bytes, base + 0x40)[0]
            ss = struct.unpack_from(">I", arc_bytes, base + 0x44)[0]
            packed = struct.unpack_from(">I", arc_bytes, base + 0x48)[0]
            off = struct.unpack_from(">I", arc_bytes, base + 0x4C)[0]
            raw_size = packed >> 3
            flags = packed & 7
            stored = arc_bytes[off:off + ss]
            codec = "raw"
            warning = None
            raw = None
            if ss == raw_size:
                raw = stored
            else:
                if len(stored) >= 2:
                    cmf, flg = stored[0], stored[1]
                    has_zlib = ((cmf & 0x0F) == 8
                                and ((cmf << 8) | flg) % 31 == 0)
                else:
                    has_zlib = False
                if not has_zlib:
                    raise ValueError(
                        f"no zlib header and stored {ss} != declared {raw_size}")
                d = zlib.decompressobj()
                out = d.decompress(stored) + d.flush()
                if d.unused_data:
                    raise ValueError("unused_data")
                if d.unconsumed_tail:
                    raise ValueError("unconsumed_tail")
                raw = out
                codec = "zlib"
                if len(raw) != raw_size:
                    warning = (f"decoded size {len(raw)} != declared "
                               f"{raw_size}")
            entries.append({
                "index": i, "name": name, "type_hash": th,
                "compressed_size": ss, "raw_size": raw_size, "flags": flags,
                "packed_size": packed, "payload_offset": off,
                "record": arc_bytes[base:base + 0x50],
                "stored": stored, "raw": raw,
                "codec": codec, "warning": warning,
            })
        return entries

    mod.parse_arc = parse_arc
    sys.modules["safe_arc"] = mod


_install_safe_arc_double()

from utage_donor_matcher_v5 import (  # noqa: E402
    InventoryRecord, Inventory, Config,
    resolve_target, analyse_providers, resolve_group,
    harness_ready_eligible, xet_shell_compatible,
    build_harness_change, build_graft_candidate,
    key_diff_reason, ascii_lower, locale_skeleton,
    structural_compat, payload_relation, content_signature,
    load_foundry_resource_csv, load_inventory_smart, _detect_foundry_csv,
    load_effective_provider_evidence, provider_evidence_key,
    enrich_inventory, parse_xet_header,
    _safe_relative, _sha256, R_TEXTURE, TYPE_HASHES,
    run_pipeline, ArcError, EffectiveProviderEvidence, _smoke_arc,
)


R_MSG = TYPE_HASHES["rGUIMessage"]


def rec(**kw):
    base = dict(
        game="UTAGE_LIVE", outer_arc_path="utage/data/a.arc", entry_index=0,
        type_hash=R_TEXTURE, internal_path="tex\\ui\\x.xet",
        stored_sha256="ST", expanded_sha256="EXP_X",
        width=512, height=256, mips=3, format=0x2A,
        outer_arc_sha256="ARC_X",
        raw_member_size=200, xet_first_surface_offset=0x20,
        xet_shell_sha256="SHELL_X",
    )
    base.update(kw)
    return InventoryRecord(**base)


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(r + "\n")


HDR = ("game,outer_arc_path,entry_index,type_hash,internal_path,"
       "stored_sha256,expanded_sha256,outer_arc_sha256,"
       "raw_member_size,xet_first_surface_offset,xet_shell_sha256,"
       "width,height,mips,format")


# ============================================================================
# ASCII / locale semantics
# ============================================================================

def test_ascii_lower_only_az():
    assert ascii_lower("ABCZ") == "abcz"


def test_ascii_lower_preserves_non_ascii():
    assert ascii_lower("café\\naïve\\Ä") == "café\\naïve\\Ä"


def test_ascii_lower_does_not_touch_latin1_uppercase():
    assert ascii_lower("É") == "É"


def test_locale_skeleton_replacement():
    assert locale_skeleton("tex\\ui\\jpn\\x.xet") == locale_skeleton("tex\\ui\\eng\\x.xet")


def test_locale_skeleton_insertion():
    assert locale_skeleton("tex\\ui\\x.xet") == locale_skeleton("tex\\ui\\eng\\x.xet")


def test_locale_skeleton_removal():
    assert locale_skeleton("tex\\ui\\jpn\\x.xet") == locale_skeleton("tex\\ui\\x.xet")


def test_locale_skeleton_unrelated_no_match():
    assert locale_skeleton("tex\\ui\\a.xet") != locale_skeleton("tex\\ui\\b.xet")


def test_slash_preserved_in_runtime_key():
    assert rec(internal_path="tex/ui/x.xet").runtime_key[1] == "tex/ui/x.xet"


def test_harness_key_normalises_slashes():
    assert rec(internal_path="tex/ui/x.xet").harness_key == \
           rec(internal_path="tex\\ui\\x.xet").harness_key


# ============================================================================
# Payload / structural helpers
# ============================================================================

def test_same_expanded_diff_stored_is_same_content():
    a = rec(stored_sha256="S1", expanded_sha256="E")
    b = rec(stored_sha256="S2", expanded_sha256="E")
    assert payload_relation(a, b) == "EXACT_EXPANDED_MATCH"
    assert content_signature(a) == content_signature(b) == ("expanded", "E")


def test_structural_incompatible_without_content_hashes():
    a = rec(width=512, height=256, expanded_sha256=None, stored_sha256=None)
    b = rec(width=256, height=256, expanded_sha256=None, stored_sha256=None)
    assert structural_compat(a, b) == "INCOMPATIBLE"
    assert payload_relation(a, b) == "UNKNOWN_COMPRESSION"


# ============================================================================
# LOCALE is discovery-only
# ============================================================================

def test_path_skeleton_only_review_required():
    t = rec(internal_path="tex\\ui\\waza2_000.xet", expanded_sha256="A")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             expanded_sha256="C", outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [], Config())
    assert res.decision == "REVIEW_REQUIRED"
    assert res.selected is None


def test_path_only_bridge_rejected():
    t = rec(internal_path="tex\\ui\\waza2_000.xet", expanded_sha256="A",
            decoded_texture_sha256="DA")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\waza2_000.xet",
              expanded_sha256="B", decoded_texture_sha256="DB")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             expanded_sha256="C", decoded_texture_sha256="DC",
             outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [Inventory([jpn])], Config())
    assert res.decision == "REVIEW_REQUIRED"


def test_fuzzy_never_auto_writes():
    t = rec(internal_path="tex\\ui\\a.xet", expanded_sha256="A")
    d = rec(game="SH_EN", internal_path="tex\\ui\\z.xet", expanded_sha256="Z",
            outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([d]), [], Config(allow_fuzzy=True))
    assert res.decision == "REVIEW_REQUIRED"
    assert res.selected is None


def test_same_dimensions_no_path_no_content_review():
    t = rec(internal_path="tex\\ui\\a.xet", expanded_sha256="A")
    d = rec(game="SH_EN", internal_path="tex\\ui\\zzz.xet", expanded_sha256="Z",
            outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([d]), [], Config(allow_fuzzy=False))
    assert res.decision == "NO_DONOR"


# ============================================================================
# Proven bridge accepted
# ============================================================================

def test_real_hash_bridge_accepted():
    t = rec(internal_path="tex\\ui\\waza2_000.xet", expanded_sha256="JPN")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\waza2_000.xet",
              expanded_sha256="JPN")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             expanded_sha256="EN", outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [Inventory([jpn])], Config())
    assert res.decision == "STRONG_SAFE_DONOR", res.warnings
    assert res.selected.class_ == "JAPANESE_BRIDGE"


def test_bridge_via_decoded_texture_hash():
    t = rec(internal_path="tex\\ui\\waza2_000.xet",
            decoded_texture_sha256="DEC", expanded_sha256=None)
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\waza2_000.xet",
              decoded_texture_sha256="DEC", expanded_sha256=None)
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             decoded_texture_sha256="DEC_EN", expanded_sha256=None,
             outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [Inventory([jpn])], Config())
    assert res.decision == "STRONG_SAFE_DONOR", res.warnings


def test_bridge_no_locale_insertion_case():
    t = rec(internal_path="tex\\ui\\waza2_000.xet", expanded_sha256="JPN")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\waza2_000.xet",
              expanded_sha256="JPN")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             expanded_sha256="EN", outer_arc_path="sh/a.arc")
    assert resolve_target(t, Inventory([en]), [Inventory([jpn])],
                          Config()).decision == "STRONG_SAFE_DONOR"


def test_bridge_locale_removal_case():
    t = rec(internal_path="tex\\ui\\jpn\\waza2_000.xet", expanded_sha256="JPN")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\jpn\\waza2_000.xet",
              expanded_sha256="JPN")
    en = rec(game="SH_EN", internal_path="tex\\ui\\waza2_000.xet",
             expanded_sha256="EN", outer_arc_path="sh/a.arc")
    assert resolve_target(t, Inventory([en]), [Inventory([jpn])],
                          Config()).decision == "STRONG_SAFE_DONOR"


def test_bridge_unrelated_path_rejected():
    t = rec(internal_path="tex\\ui\\a.xet", expanded_sha256="JPN")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\a.xet",
              expanded_sha256="JPN")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\b.xet",
             expanded_sha256="EN", outer_arc_path="sh/a.arc")
    assert resolve_target(t, Inventory([en]), [Inventory([jpn])],
                          Config()).decision == "NO_DONOR"


# ============================================================================
# Harness vs graft
# ============================================================================

def test_same_key_sh_donor_produces_harness_change():
    t = rec(expanded_sha256="EXP_T", outer_arc_sha256="ARC_T")
    en = rec(game="SH_EN", expanded_sha256="EXP_E", outer_arc_sha256="ARC_E",
             outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [], Config())
    assert res.decision == "EXACT_SAFE_DONOR"
    ok, reason = harness_ready_eligible(res.target, res.selected.donor)
    assert ok, reason
    ch = build_harness_change(res.target, res.selected.donor, Config())
    assert ch.expected_raw_sha256 == "EXP_T"
    assert ch.donor_raw_sha256 == "EXP_E"


def test_different_key_sh_donor_is_graft_not_harness():
    t = rec(internal_path="tex\\ui\\waza2_000.xet",
            expanded_sha256="JPN", outer_arc_sha256="ARC_T")
    jpn = rec(game="SB3_JPN", internal_path="tex\\ui\\waza2_000.xet",
              expanded_sha256="JPN")
    en = rec(game="SH_EN", internal_path="tex\\ui\\eng\\waza2_000.xet",
             expanded_sha256="EN", outer_arc_sha256="ARC_E",
             outer_arc_path="sh/a.arc")
    res = resolve_target(t, Inventory([en]), [Inventory([jpn])], Config())
    assert res.decision == "STRONG_SAFE_DONOR"
    ok, reason = harness_ready_eligible(res.target, res.selected.donor)
    assert not ok and reason == "harness_key_mismatch"
    assert key_diff_reason(res.target, res.selected.donor) == "locale_segment_differs"


def test_xet_shell_mismatch_not_harness_ready():
    ok, reason = harness_ready_eligible(rec(xet_shell_sha256="A"),
                                        rec(game="SH_EN", xet_shell_sha256="B",
                                            outer_arc_path="sh/a.arc"))
    assert not ok and reason == "shell_sha256_mismatch"


def test_xet_missing_shell_evidence_not_harness_ready():
    ok, reason = harness_ready_eligible(rec(xet_shell_sha256=None),
                                        rec(game="SH_EN", xet_shell_sha256="B",
                                            outer_arc_path="sh/a.arc"))
    assert not ok and reason == "missing_shell_sha256"


def test_xet_raw_member_size_mismatch_not_harness_ready():
    ok, reason = harness_ready_eligible(rec(raw_member_size=200),
                                        rec(game="SH_EN", raw_member_size=300,
                                            outer_arc_path="sh/a.arc"))
    assert not ok and reason == "raw_member_size_mismatch"


def test_xet_first_surface_offset_mismatch_not_harness_ready():
    ok, reason = harness_ready_eligible(rec(xet_first_surface_offset=0x20),
                                        rec(game="SH_EN", xet_first_surface_offset=0x30,
                                            outer_arc_path="sh/a.arc"))
    assert not ok and reason == "surface_offset_mismatch"


def test_xet_matching_shell_evidence_is_harness_ready():
    ok, reason = harness_ready_eligible(rec(),
                                        rec(game="SH_EN", outer_arc_path="sh/a.arc"))
    assert ok, reason


# ============================================================================
# Non-texture classes
# ============================================================================

def test_non_texture_exact_path_is_review_required():
    t = rec(type_hash=R_MSG, internal_path="msg\\versus.msg",
            width=None, height=None, mips=None, format=None,
            expanded_sha256=None, stored_sha256=None)
    en = rec(game="SH_EN", type_hash=R_MSG, internal_path="msg\\versus.msg",
             width=None, height=None, mips=None, format=None,
             expanded_sha256=None, stored_sha256=None,
             outer_arc_path="sh/a.arc")
    assert resolve_target(t, Inventory([en]), [], Config()).decision == "REVIEW_REQUIRED"


def test_non_texture_with_content_identity_is_safe():
    t = rec(type_hash=R_MSG, internal_path="msg\\a.msg",
            expanded_sha256="X", width=None, height=None, mips=None, format=None)
    en = rec(game="SH_EN", type_hash=R_MSG, internal_path="msg\\eng\\a.msg",
             expanded_sha256="X", width=None, height=None, mips=None, format=None,
             outer_arc_path="sh/a.arc")
    assert resolve_target(t, Inventory([en]), [],
                          Config()).decision == "STRONG_SAFE_DONOR"


# ============================================================================
# Group / provider policy
# ============================================================================

def _make_group(n, expanded_sig="EXP_T", shell="SHELL_T"):
    return [rec(outer_arc_path=f"utage/{i}.arc", entry_index=i,
                expanded_sha256=expanded_sig, outer_arc_sha256=f"ARC_T{i}",
                xet_shell_sha256=shell, raw_member_size=200,
                xet_first_surface_offset=0x20) for i in range(n)]


def _make_en():
    return rec(game="SH_EN", outer_arc_path="sh/a.arc", entry_index=0,
               expanded_sha256="EXP_E", outer_arc_sha256="ARC_E",
               xet_shell_sha256="SHELL_T",
               raw_member_size=200, xet_first_surface_offset=0x20)


def test_single_provider_emits_change():
    gd = resolve_group(_make_group(1), Inventory([_make_en()]), [], Config(), {})
    assert gd.resolution.provider_status == "EMIT_SINGLE"
    assert len(gd.actions) == 1 and gd.actions[0].kind == "HARNESS"


def test_two_identical_providers_report_only_no_evidence():
    gd = resolve_group(_make_group(2), Inventory([_make_en()]), [],
                       Config(duplicate_policy="REPORT_ONLY"), {})
    assert gd.resolution.provider_status == "PROVIDER_SELECTION_REQUIRED"
    assert len(gd.actions) == 0


def test_two_identical_providers_sync_emits_two():
    gd = resolve_group(_make_group(2), Inventory([_make_en()]), [],
                       Config(duplicate_policy="SYNC_EXACT_PROVIDERS"), {})
    assert gd.resolution.provider_status == "EMIT_SYNC"
    assert len(gd.actions) == 2
    assert all(a.kind == "HARNESS" for a in gd.actions)


def test_divergent_providers_no_evidence_no_changes():
    provs = [rec(outer_arc_path="utage/a.arc", entry_index=0,
                 expanded_sha256="EXP_1", xet_shell_sha256="SHELL_T"),
             rec(outer_arc_path="utage/b.arc", entry_index=5,
                 expanded_sha256="EXP_2", xet_shell_sha256="SHELL_T")]
    en = _make_en()
    for pol in ("REPORT_ONLY", "SYNC_EXACT_PROVIDERS"):
        gd = resolve_group(provs, Inventory([en]), [],
                           Config(duplicate_policy=pol), {})
        assert gd.resolution.provider_status == "REVIEW_PROVIDER_ORDER"
        assert len(gd.actions) == 0


def test_divergent_providers_with_evidence_emits_effective():
    """Provider and donor shells match; evidence selects provider b.arc#5."""
    provs = [rec(outer_arc_path="utage/a.arc", entry_index=0,
                 expanded_sha256="EXP_1", outer_arc_sha256="ARC_A",
                 xet_shell_sha256="SHELL_T"),
             rec(outer_arc_path="utage/b.arc", entry_index=5,
                 expanded_sha256="EXP_2", outer_arc_sha256="ARC_B",
                 xet_shell_sha256="SHELL_T")]
    en = _make_en()  # SHELL_T, matching
    ev = EffectiveProviderEvidence("utage/b.arc", 5, "RPCS3 log")
    key = provider_evidence_key(provs[0].runtime_key)
    gd = resolve_group(provs, Inventory([en]), [], Config(), {key: ev})
    assert gd.resolution.provider_status == "EMIT_EFFECTIVE_PROVIDER"
    assert len(gd.actions) == 1
    assert gd.actions[0].provider.outer_arc_path == "utage/b.arc"


def test_divergent_providers_with_evidence_but_shell_mismatch_is_ineligible():
    """Same scenario but provider shell does not match donor -> ineligible."""
    provs = [rec(outer_arc_path="utage/a.arc", entry_index=0,
                 expanded_sha256="EXP_1", xet_shell_sha256="SHELL_X"),
             rec(outer_arc_path="utage/b.arc", entry_index=5,
                 expanded_sha256="EXP_2", xet_shell_sha256="SHELL_X")]
    en = _make_en()  # SHELL_T -> mismatch
    ev = EffectiveProviderEvidence("utage/b.arc", 5, "trace")
    key = provider_evidence_key(provs[0].runtime_key)
    gd = resolve_group(provs, Inventory([en]), [], Config(), {key: ev})
    assert gd.resolution.provider_status == "REVIEW_EFFECTIVE_INELIGIBLE"
    assert len(gd.actions) == 0


def test_unsafe_sibling_blocks_sync():
    provs = [rec(outer_arc_path="utage/a.arc", entry_index=0,
                 expanded_sha256="EXP_T", xet_shell_sha256="SHELL_T"),
             rec(outer_arc_path="utage/b.arc", entry_index=1,
                 expanded_sha256="EXP_T", xet_shell_sha256="SHELL_X")]
    en = _make_en()
    gd = resolve_group(provs, Inventory([en]), [],
                       Config(duplicate_policy="SYNC_EXACT_PROVIDERS"), {})
    assert gd.resolution.provider_status == "REVIEW_INCOMPATIBLE_SIBLING"
    assert len(gd.actions) == 0


# ============================================================================
# Foundry adapter
# ============================================================================

def test_foundry_resource_ownership_csv_import(tmp_path):
    csv_path = tmp_path / "foundry.csv"
    csv_path.write_text(
        "arc,index,physical_path,exact_path,locale_equiv_path,type_hex,type_name,"
        "stored_size,expanded_size,flags,data_offset,stored_sha256,expanded_sha256,"
        "decode_method,bounds_ok\n"
        "/data/title_id.arc,12,tex/ui/waza2_000.xet,tex\\ui\\waza2_000.xet,"
        "tex/ui/<LOCALE>/waza2_000.xet,241F5DEB,rTexture,4096,16384,0,128,"
        "aaaaaaaa,bbbbbbbb,zlib,true\n",
        encoding="utf-8")
    r = load_foundry_resource_csv(str(csv_path), default_game="UTAGE_LIVE")[0]
    assert r.outer_arc_path == "/data/title_id.arc"
    assert r.entry_index == 12
    assert r.internal_path == "tex\\ui\\waza2_000.xet"
    assert r.type_hash == 0x241F5DEB
    assert r.extra.get("decode_method") == "zlib"
    assert r.extra.get("bounds_ok") == "true"
    assert r.extra.get("data_offset") == "128"


def test_foundry_detection(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text("arc,index,type_hex\na.arc,0,0x241F5DEB\n", encoding="utf-8")
    assert _detect_foundry_csv(str(f))
    g = tmp_path / "g.csv"
    g.write_text("game,outer_arc_path,entry_index,type_hash\nX,a.arc,0,0x241F5DEB\n",
                 encoding="utf-8")
    assert not _detect_foundry_csv(str(g))


# ============================================================================
# Path rebasing
# ============================================================================

def test_path_rebase_common_root():
    cfg = Config(harness_root="E:\\",
                 utage_prefix="Utage Patching New",
                 sh_prefix="SAMURAI HEROES")
    t = rec(outer_arc_path="eng\\title.arc", expanded_sha256="EXP_T",
            outer_arc_sha256="ARC_T")
    e = rec(game="SH_EN", outer_arc_path="eng\\title.arc",
            expanded_sha256="EXP_E", outer_arc_sha256="ARC_E")
    ch = build_harness_change(t, e, cfg)
    assert ch.arc == "Utage Patching New\\eng\\title.arc"
    assert ch.donor_arc == "SAMURAI HEROES\\eng\\title.arc"


def test_path_escape_absolute_rejected():
    for bad in ("C:\\a\\b.arc", "\\abs\\a.arc", "/abs/a.arc",
                "..\\esc\\a.arc", "a/../b.arc"):
        with pytest.raises(ValueError):
            _safe_relative(bad)


def test_path_escape_relative_accepted():
    assert _safe_relative("eng\\title.arc") == "eng\\title.arc"
    assert _safe_relative("eng/title.arc") == "eng\\title.arc"


# ============================================================================
# Real-format synthetic ARC fixtures
# ============================================================================

def _build_arc_v8(entries):
    """
    entries: list of (path, type_hash, raw_bytes, flags, compress)
    Real layout: b"\\0CRA" + u16 version + u16 count (8 bytes) then entries.
    """
    n = len(entries)
    header = b"\0CRA" + struct.pack(">HH", 8, n)
    assert len(header) == 8
    data_base = 8 + n * 0x50
    table = b""
    blob = b""
    for path, th, raw, flags, compress in entries:
        pb = path.encode("latin-1")
        assert len(pb) < 64
        stored = zlib.compress(raw) if compress else raw
        ss = len(stored)
        packed = (len(raw) << 3) | (flags & 7)
        off = data_base + len(blob)
        table += pb + b"\0" * (64 - len(pb))
        table += struct.pack(">IIII", th, ss, packed, off)
        blob += stored
    return header + table + blob


def _build_xet(width, height, mips, fmt, payload_size=64, fill=0xFF):
    flags = ((mips & 0x3F) | ((width & 0x1FFF) << 6) | ((height & 0x1FFF) << 19))
    prefix = bytearray(20)
    prefix[0:4] = b"\0XET"
    struct.pack_into(">I", prefix, 0x08, flags)
    prefix[0x0E] = fmt
    struct.pack_into(">I", prefix, 0x10, 20)
    return bytes(prefix) + bytes([fill]) * payload_size


# --- safe_arc-double regression tests --------------------------------------

def test_safe_arc_double_uncompressed_one_entry(tmp_path):
    xet = _build_xet(512, 256, 3, 0x2A, payload_size=64)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\a.xet")
    enrich_inventory([r], str(tmp_path))
    assert r.outer_arc_sha256 == _sha256(arc_bytes)
    assert r.stored_sha256 == _sha256(xet)
    assert r.expanded_sha256 == _sha256(xet)
    assert r.raw_member_size == len(xet)
    assert r.width == 512 and r.height == 256
    assert r.mips == 3 and r.format == 0x2A
    assert r.xet_first_surface_offset == 20
    assert r.xet_shell_sha256 == _sha256(xet[:20])


def test_safe_arc_double_compressed_one_entry(tmp_path):
    xet = _build_xet(128, 128, 2, 0x19, payload_size=128)
    arc_bytes = _build_arc_v8([("tex\\ui\\b.xet", R_TEXTURE, xet, 3, True)])
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\b.xet")
    enrich_inventory([r], str(tmp_path))
    assert r.stored_sha256 != r.expanded_sha256  # compressed vs raw
    assert r.expanded_sha256 == _sha256(xet)
    assert r.raw_member_size == len(xet)


def test_safe_arc_double_nonzero_flags(tmp_path):
    xet = _build_xet(64, 64, 1, 0x19, payload_size=32)
    arc_bytes = _build_arc_v8([("tex\\ui\\c.xet", R_TEXTURE, xet, 5, False)])
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\c.xet")
    enrich_inventory([r], str(tmp_path))
    assert r.expanded_sha256 == _sha256(xet)


def test_safe_arc_double_zlib_size_disagreement_warning(tmp_path):
    """safe_arc returns warning when decoded length != declared raw_size."""
    raw = b"hello world" * 10
    compressed = zlib.compress(raw)
    # intentionally declare raw_size one byte larger
    declared_raw_size = len(raw) + 1
    n = 1
    header = b"\0CRA" + struct.pack(">HH", 8, n)
    data_base = 8 + n * 0x50
    table = b""
    pb = b"msg\\warning_fixture"
    table += pb + b"\0" * (64 - len(pb))
    packed = (declared_raw_size << 3) | 0
    non_texture_type = 0x12345678
    table += struct.pack(">IIII", non_texture_type, len(compressed), packed, data_base)
    arc_bytes = header + table + compressed
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=non_texture_type, internal_path="msg\\warning_fixture")
    enrich_inventory([r], str(tmp_path))
    # safe_arc preserves ACTUAL decoded bytes; warning issued but not raised
    assert r.expanded_sha256 == _sha256(raw)
    assert r.raw_member_size == len(raw)


def test_safe_arc_double_malformed_zlib_fails_closed(tmp_path):
    raw = b"payload" * 30
    compressed = zlib.compress(raw)
    corrupted = bytearray(compressed)
    corrupted[-3] ^= 0xFF  # corrupt
    n = 1
    header = b"\0CRA" + struct.pack(">HH", 8, n)
    data_base = 8 + n * 0x50
    table = b""
    pb = b"tex\\ui\\e.xet"
    table += pb + b"\0" * (64 - len(pb))
    packed = (len(raw) << 3) | 0
    table += struct.pack(">IIII", R_TEXTURE, len(corrupted), packed, data_base)
    arc_bytes = header + table + bytes(corrupted)
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\e.xet")
    with pytest.raises(Exception):
        enrich_inventory([r], str(tmp_path))


def test_safe_arc_double_no_zlib_header_and_sizes_differ_fails(tmp_path):
    """stored != declared raw and no zlib header -> fail closed."""
    stored = b"not zlib at all"
    declared_raw = len(stored) + 10
    n = 1
    header = b"\0CRA" + struct.pack(">HH", 8, n)
    data_base = 8 + n * 0x50
    table = b""
    pb = b"tex\\ui\\f.xet"
    table += pb + b"\0" * (64 - len(pb))
    packed = (declared_raw << 3) | 0
    table += struct.pack(">IIII", R_TEXTURE, len(stored), packed, data_base)
    arc_bytes = header + table + stored
    arc_path = tmp_path / "data.arc"
    arc_path.write_bytes(arc_bytes)

    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\f.xet")
    with pytest.raises(Exception):
        enrich_inventory([r], str(tmp_path))


def test_enrichment_path_mismatch_rejected(tmp_path):
    xet = _build_xet(64, 64, 1, 0x19)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    (tmp_path / "data.arc").write_bytes(arc_bytes)
    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\WRONG.xet")
    with pytest.raises(ArcError):
        enrich_inventory([r], str(tmp_path))


def test_enrichment_type_mismatch_rejected(tmp_path):
    xet = _build_xet(64, 64, 1, 0x19)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    (tmp_path / "data.arc").write_bytes(arc_bytes)
    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=0,
                        type_hash=0xDEADBEEF, internal_path="tex\\ui\\a.xet")
    with pytest.raises(ArcError):
        enrich_inventory([r], str(tmp_path))


def test_enrichment_index_out_of_range_rejected(tmp_path):
    xet = _build_xet(64, 64, 1, 0x19)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    (tmp_path / "data.arc").write_bytes(arc_bytes)
    r = InventoryRecord(game="U", outer_arc_path="data.arc", entry_index=5,
                        type_hash=R_TEXTURE, internal_path="tex\\ui\\a.xet")
    with pytest.raises(ArcError):
        enrich_inventory([r], str(tmp_path))


def test_target_and_sh_trees_remain_distinct(tmp_path):
    u = tmp_path / "utage"
    s = tmp_path / "sh"
    u.mkdir(); s.mkdir()
    ux = _build_xet(64, 64, 1, 0x19, payload_size=32, fill=0xAA)
    sx = _build_xet(64, 64, 1, 0x19, payload_size=32, fill=0xBB)  # different
    (u / "title.arc").write_bytes(
        _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, ux, 0, False)]))
    (s / "title.arc").write_bytes(
        _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, sx, 0, False)]))

    ru = InventoryRecord(game="U", outer_arc_path="title.arc", entry_index=0,
                         type_hash=R_TEXTURE, internal_path="tex\\ui\\a.xet")
    rs = InventoryRecord(game="E", outer_arc_path="title.arc", entry_index=0,
                         type_hash=R_TEXTURE, internal_path="tex\\ui\\a.xet")
    enrich_inventory([ru], str(u))
    enrich_inventory([rs], str(s))
    assert ru.outer_arc_sha256 != rs.outer_arc_sha256
    assert ru.expanded_sha256 != rs.expanded_sha256


def test_xet_header_parsing():
    raw = _build_xet(2048, 1024, 5, 0x17)
    h = parse_xet_header(raw)
    assert h.width == 2048 and h.height == 1024
    assert h.mips == 5 and h.format == 0x17
    assert h.first_surface_offset == 20


def test_xet_bad_magic_rejected():
    with pytest.raises(ArcError):
        parse_xet_header(b"\0XXX" + b"\0" * 32)


def test_xet_bad_offset_rejected():
    raw = bytearray(_build_xet(64, 64, 1, 0x19))
    struct.pack_into(">I", raw, 0x10, 5)
    with pytest.raises(ArcError):
        parse_xet_header(bytes(raw))


def test_real_format_no_0x10_table_start(tmp_path):
    """Regression: table must start at 0x08, not 0x10."""
    xet = _build_xet(64, 64, 1, 0x19, payload_size=32)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    # The first entry path bytes must be at 0x08, not 0x10.
    assert arc_bytes[8:8 + 4] == b"tex\\"[0:4]
    # And the entry type hash is at 0x08 + 0x40.
    th = struct.unpack_from(">I", arc_bytes, 8 + 0x40)[0]
    assert th == R_TEXTURE


# ============================================================================
# Effective provider evidence JSON
# ============================================================================

def test_provider_evidence_load(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({
        "0x241F5DEB|tex\\ui\\a.xet": {
            "effective_arc": "utage/b.arc",
            "effective_index": 5,
            "evidence": "RPCS3 log",
        }
    }), encoding="utf-8")
    ev = load_effective_provider_evidence(str(p))
    key = provider_evidence_key((R_TEXTURE, "tex\\ui\\a.xet"))
    assert key in ev and ev[key].effective_index == 5


# ============================================================================
# End-to-end
# ============================================================================

def test_end_to_end(tmp_path):
    utage = tmp_path / "utage.csv"
    _write_csv(utage, HDR, [
        "UTAGE_LIVE,utage/data/title_id.arc,1,0x241F5DEB,tex\\ui\\a.xet,"
        "RAW_T,EXP_T,ARC_T,200,32,SHELL_T,512,256,3,0x2A",
        "UTAGE_LIVE,utage/data/title_id.arc,2,0x241F5DEB,tex\\ui\\waza2_000.xet,"
        "RAW_T2,EXP_JPN,ARC_T2,200,32,SHELL_T2,512,256,3,0x2A",
    ])
    sb3 = tmp_path / "sb3.csv"
    _write_csv(sb3, HDR, [
        "SB3_JPN,sb3/data/title.arc,2,0x241F5DEB,tex\\ui\\waza2_000.xet,"
        "RAW_J,EXP_JPN,ARC_J,200,32,SHELL_J,512,256,3,0x2A",
    ])
    sh_en = tmp_path / "sh_en.csv"
    _write_csv(sh_en, HDR, [
        "SH_EN,sh_en/data/title.arc,1,0x241F5DEB,tex\\ui\\a.xet,"
        "RAW_E1,EXP_E1,ARC_E1,200,32,SHELL_T,512,256,3,0x2A",
        "SH_EN,sh_en/data/title.arc,2,0x241F5DEB,tex\\ui\\eng\\waza2_000.xet,"
        "RAW_E2,EXP_EN,ARC_E2,200,32,SHELL_E2,512,256,3,0x2A",
    ])
    cfg = Config(harness_root="E:\\",
                 utage_prefix="Utage Patching New",
                 sh_prefix="SAMURAI HEROES")
    summary = run_pipeline(cfg, str(utage), str(sh_en),
                           [("SB3_JPN", str(sb3))],
                           str(tmp_path / "r.json"),
                           str(tmp_path / "h.json"),
                           str(tmp_path / "g.json"))
    assert summary["targets"] == 2
    assert summary["harness_ready_changes"] == 1
    assert summary["graft_candidates"] == 1
    plan = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    assert plan["changes"][0]["arc"] == \
        "Utage Patching New\\utage\\data\\title_id.arc"
    assert plan["changes"][0]["expected_raw_sha256"] == "EXP_T"
    gp = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
    g = gp["candidates"][0]
    assert g["harness_eligibility_failure"] == "harness_key_mismatch"
    assert g["key_difference"] == "locale_segment_differs"


def test_end_to_end_with_enrichment(tmp_path):
    ux = _build_xet(512, 256, 3, 0x2A, payload_size=64, fill=0xAA)
    u_arc = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, ux, 0, False)])
    (tmp_path / "utage_arcs").mkdir()
    (tmp_path / "utage_arcs" / "title.arc").write_bytes(u_arc)

    ex = _build_xet(512, 256, 3, 0x2A, payload_size=64, fill=0xAA)
    e_arc = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, ex, 0, False)])
    (tmp_path / "sh_arcs").mkdir()
    (tmp_path / "sh_arcs" / "title.arc").write_bytes(e_arc)

    utage = tmp_path / "u.csv"
    _write_csv(utage, "game,outer_arc_path,entry_index,type_hash,internal_path", [
        "U,title.arc,0,0x241F5DEB,tex\\ui\\a.xet",
    ])
    sh = tmp_path / "s.csv"
    _write_csv(sh, "game,outer_arc_path,entry_index,type_hash,internal_path", [
        "E,title.arc,0,0x241F5DEB,tex\\ui\\a.xet",
    ])
    cfg = Config(harness_root="E:\\", utage_prefix="Utage", sh_prefix="SH",
                 utage_root=str(tmp_path / "utage_arcs"),
                 sh_root=str(tmp_path / "sh_arcs"))
    summary = run_pipeline(cfg, str(utage), str(sh), [],
                           str(tmp_path / "r.json"),
                           str(tmp_path / "h.json"),
                           str(tmp_path / "g.json"))
    assert summary["harness_ready_changes"] == 1


def test_cli_runs(tmp_path):
    utage = tmp_path / "u.csv"
    _write_csv(utage, HDR, [
        "U,data/a.arc,0,0x241F5DEB,tex\\ui\\a.xet,ST,EXP_T,ARC_T,200,32,SHELL_T,512,256,3,0x2A",
    ])
    sh_en = tmp_path / "e.csv"
    _write_csv(sh_en, HDR, [
        "E,data/a.arc,0,0x241F5DEB,tex\\ui\\a.xet,SE,EXP_E,ARC_E,200,32,SHELL_T,512,256,3,0x2A",
    ])
    from utage_donor_matcher_v5 import _main
    rc = _main([
        "--utage", str(utage), "--sh-en", str(sh_en),
        "--report", str(tmp_path / "r.json"),
        "--harness-plan", str(tmp_path / "h.json"),
        "--graft-plan", str(tmp_path / "g.json"),
        "--harness-root", "E:\\",
        "--utage-prefix", "Utage",
        "--sh-prefix", "SH",
    ])
    assert rc == 0
    plan = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    assert plan["changes"][0]["arc"] == "Utage\\data\\a.arc"


def test_cli_smoke_arc(tmp_path):
    xet = _build_xet(64, 64, 1, 0x19, payload_size=32)
    arc_bytes = _build_arc_v8([("tex\\ui\\a.xet", R_TEXTURE, xet, 0, False)])
    arc_path = tmp_path / "smoke.arc"
    arc_path.write_bytes(arc_bytes)
    from utage_donor_matcher_v5 import _main
    rc = _main(["--smoke-arc", str(arc_path), "--smoke-limit", "1"])
    assert rc == 0