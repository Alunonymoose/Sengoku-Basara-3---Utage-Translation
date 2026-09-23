# utage_donor_matcher_v5.py
"""
V5 — uses safe_arc.parse_arc as the SINGLE authoritative ARC parser.
No custom ARC parser. No raw-deflate fallback.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import re
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


TYPE_HASHES = {
    "rArchive": 0x73850D05, "rTexture": 0x241F5DEB,
    "rGUIMessage": 0x242BB29A, "rGUIFont": 0x2D462600,
    "rGUI": 0x22948394, "rNameId": 0x6450A37A,
    "rLayoutParameter": 0x0C41C74D, "lsp": 0x60DD1B16,
}
R_TEXTURE = TYPE_HASHES["rTexture"]
VALIDATED_CLASSES = frozenset({R_TEXTURE})

LOCALE_SEGMENTS = frozenset({
    "jpn", "jp", "jap", "eng", "en", "usa", "us", "eur", "uk",
    "fra", "deu", "ita", "esp",
})
_SPLIT_RE = re.compile(r"[\\/]+")


class ArcError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# ASCII / locale helpers
# ---------------------------------------------------------------------------

def ascii_lower(s: str) -> str:
    return "".join(chr(ord(c) + 0x20) if 0x41 <= ord(c) <= 0x5A else c for c in s)


def locale_skeleton(path: str) -> str:
    parts = _SPLIT_RE.split(path)
    kept = [ascii_lower(p) for p in parts if p and p.lower() not in LOCALE_SEGMENTS]
    return "/".join(kept)


def locale_variant_key(path: str) -> str:
    return locale_skeleton(path)


def normalize_path_for_evidence(p: str) -> str:
    return ascii_lower(p.replace("/", "\\"))


# ---------------------------------------------------------------------------
# safe_arc integration
# ---------------------------------------------------------------------------

_safe_arc_cache: Any = None


def _import_safe_arc():
    """Return the production safe_arc module. Lazy so tests can inject one."""
    global _safe_arc_cache
    if _safe_arc_cache is not None:
        return _safe_arc_cache
    try:
        mod = importlib.import_module("safe_arc")
    except ImportError as e:
        raise ArcError(
            "safe_arc.py is required for ARC enrichment and must be importable. "
            f"ImportError: {e}")
    if not hasattr(mod, "parse_arc"):
        raise ArcError("safe_arc.parse_arc not found")
    _safe_arc_cache = mod
    return mod


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class InventoryRecord:
    game: str
    outer_arc_path: str
    entry_index: int
    type_hash: int
    internal_path: str
    stored_size: int = 0
    expanded_size: int = 0
    flags: int = 0
    stored_sha256: Optional[str] = None
    expanded_sha256: Optional[str] = None
    decoded_texture_sha256: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mips: Optional[int] = None
    format: Optional[int] = None
    surface_count: Optional[int] = None
    outer_arc_sha256: Optional[str] = None
    raw_member_size: Optional[int] = None
    xet_first_surface_offset: Optional[int] = None
    xet_shell_sha256: Optional[str] = None
    equivalence_group: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def runtime_key(self) -> Tuple[int, str]:
        return (self.type_hash, ascii_lower(self.internal_path))

    @property
    def harness_key(self) -> Tuple[int, str]:
        return (self.type_hash, ascii_lower(self.internal_path.replace("/", "\\")))


@dataclass
class Match:
    target: InventoryRecord
    donor: InventoryRecord
    class_: str
    evidence: List[Dict[str, Any]]
    structural_compat: str
    payload_relation: str
    warnings: List[str] = field(default_factory=list)
    bridge_path: Optional[List[Dict[str, Any]]] = None

    @property
    def confidence_level(self) -> str:
        return {"EXACT": "A", "LOCALE": "B", "JAPANESE_BRIDGE": "C",
                "CONTENT": "D", "FUZZY_STRUCTURE": "E"}.get(self.class_, "E")


@dataclass
class Resolution:
    target: InventoryRecord
    direct_matches: List[Match]
    bridge_matches: List[Match]
    decision: str
    selected: Optional[Match]
    warnings: List[str] = field(default_factory=list)
    provider_analysis: Optional[Dict[str, Any]] = None
    provider_status: str = ""
    provider_messages: List[str] = field(default_factory=list)


@dataclass
class HarnessChange:
    arc: str
    index: int
    name: str
    type_hash: int
    expected_raw_sha256: str
    source_arc_sha256: str
    donor_arc: str
    donor_index: int
    donor_raw_sha256: str
    donor_source_sha256: str


@dataclass
class GraftCandidate:
    target_arc: str
    target_index: int
    target_path: str
    target_type_hash: int
    target_stored_sha256: Optional[str]
    target_expanded_sha256: Optional[str]
    target_raw_member_size: Optional[int]
    target_xet_first_surface_offset: Optional[int]
    target_xet_shell_sha256: Optional[str]
    target_width: Optional[int]
    target_height: Optional[int]
    target_mips: Optional[int]
    target_format: Optional[int]

    donor_arc: str
    donor_index: int
    donor_path: str
    donor_type_hash: int
    donor_stored_sha256: Optional[str]
    donor_expanded_sha256: Optional[str]
    donor_raw_member_size: Optional[int]
    donor_xet_first_surface_offset: Optional[int]
    donor_xet_shell_sha256: Optional[str]
    donor_width: Optional[int]
    donor_height: Optional[int]
    donor_mips: Optional[int]
    donor_format: Optional[int]

    match_class: str
    confidence_level: str
    structural_compatibility: str
    payload_relation: str
    harness_eligibility_failure: str
    key_difference: str
    required_operation: str
    evidence: List[Dict[str, Any]]
    bridge_path: Optional[List[Dict[str, Any]]]
    provider_analysis: Optional[Dict[str, Any]]
    provider_status: str
    warnings: List[str]


@dataclass
class Config:
    harness_root: str = ""
    utage_prefix: str = ""
    sh_prefix: str = ""
    utage_root: str = ""
    sh_root: str = ""
    effective_provider_evidence_path: str = ""
    allow_fuzzy: bool = False
    duplicate_policy: str = "REPORT_ONLY"
    require_structural_validator: bool = True


@dataclass
class EffectiveProviderEvidence:
    effective_arc: str
    effective_index: int
    evidence: str = ""


# ---------------------------------------------------------------------------
# Generic loaders
# ---------------------------------------------------------------------------

def _parse_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    if v is None or v == "":
        return default
    if isinstance(v, int):
        return v
    s = str(v).strip()
    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        if re.fullmatch(r"[0-9A-Fa-f]+", s) and re.search(r"[A-Fa-f]", s):
            return int(s, 16)
        return int(s)
    except ValueError:
        return default


def _row_to_record(row: Dict[str, Any], default_game: Optional[str] = None) -> InventoryRecord:
    g = row.get("game") or default_game or "UNKNOWN"
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    return InventoryRecord(
        game=g,
        outer_arc_path=str(row.get("outer_arc_path") or ""),
        entry_index=_parse_int(row.get("entry_index"), 0) or 0,
        type_hash=_parse_int(row.get("type_hash"), 0) or 0,
        internal_path=str(row.get("internal_path") or ""),
        stored_size=_parse_int(row.get("stored_size"), 0) or 0,
        expanded_size=_parse_int(row.get("expanded_size"), 0) or 0,
        flags=_parse_int(row.get("flags"), 0) or 0,
        stored_sha256=row.get("stored_sha256") or None,
        expanded_sha256=row.get("expanded_sha256") or None,
        decoded_texture_sha256=row.get("decoded_texture_sha256") or None,
        width=_parse_int(row.get("width")),
        height=_parse_int(row.get("height")),
        mips=_parse_int(row.get("mips")),
        format=_parse_int(row.get("format")),
        surface_count=_parse_int(row.get("surface_count")),
        outer_arc_sha256=row.get("outer_arc_sha256") or None,
        raw_member_size=_parse_int(row.get("raw_member_size")),
        xet_first_surface_offset=_parse_int(row.get("xet_first_surface_offset")),
        xet_shell_sha256=row.get("xet_shell_sha256") or None,
        equivalence_group=row.get("equivalence_group") or None,
        extra=dict(extra),
    )


def load_inventory_csv(path, default_game=None):
    with open(path, newline="", encoding="utf-8") as f:
        return [_row_to_record(r, default_game) for r in csv.DictReader(f)]


def load_inventory_json(path, default_game=None):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data["records"] if isinstance(data, dict) and "records" in data else data
    return [_row_to_record(r, default_game) for r in rows]


def load_inventory(path, default_game=None):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return load_inventory_json(path, default_game)
    if ext == ".csv":
        return load_inventory_csv(path, default_game)
    try:
        return load_inventory_json(path, default_game)
    except Exception:
        return load_inventory_csv(path, default_game)


_FOUNDRY_MAP = {
    "arc": "outer_arc_path", "index": "entry_index",
    "physical_path": "internal_path", "exact_path": "internal_path",
    "type_hex": "type_hash", "type_name": "extra.type_name",
    "stored_size": "stored_size", "expanded_size": "expanded_size",
    "flags": "flags", "data_offset": "extra.data_offset",
    "stored_sha256": "stored_sha256", "expanded_sha256": "expanded_sha256",
    "decode_method": "extra.decode_method", "bounds_ok": "extra.bounds_ok",
    "locale_equiv_path": "extra.locale_equiv_path",
    "decoded_texture_sha256": "decoded_texture_sha256",
    "width": "width", "height": "height", "mips": "mips", "format": "format",
    "surface_count": "surface_count", "outer_arc_sha256": "outer_arc_sha256",
    "raw_member_size": "raw_member_size",
    "xet_first_surface_offset": "xet_first_surface_offset",
    "xet_shell_sha256": "xet_shell_sha256",
    "equivalence_group": "equivalence_group",
}


def _set_nested(d, dotted, value):
    if "." not in dotted:
        d[dotted] = value
        return
    a, b = dotted.split(".", 1)
    d.setdefault(a, {})[b] = value


def load_foundry_resource_csv(path, default_game=None):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mapped: Dict[str, Any] = {}
            for k, v in row.items():
                key = (k or "").strip().lower()
                if not key or v is None or v == "":
                    continue
                t = _FOUNDRY_MAP.get(key)
                if t is None:
                    _set_nested(mapped, f"extra.{key}", v)
                else:
                    _set_nested(mapped, t, v)
            if row.get("exact_path"):
                mapped["internal_path"] = row["exact_path"]
            elif row.get("physical_path") and "internal_path" not in mapped:
                mapped["internal_path"] = row["physical_path"]
            if default_game and "game" not in mapped:
                mapped["game"] = default_game
            out.append(_row_to_record(mapped, default_game))
    out.sort(key=lambda r: (r.outer_arc_path, r.entry_index, ascii_lower(r.internal_path)))
    return out


def _detect_foundry_csv(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
    except Exception:
        return False
    headers = {h.strip().lower() for h in header if h}
    return {"arc", "index", "type_hex"} <= headers


def load_inventory_smart(path, fmt="auto", default_game=None):
    if fmt == "foundry":
        return load_foundry_resource_csv(path, default_game)
    if fmt == "generic":
        return load_inventory(path, default_game)
    if path.lower().endswith(".csv") and _detect_foundry_csv(path):
        return load_foundry_resource_csv(path, default_game)
    return load_inventory(path, default_game)


# ---------------------------------------------------------------------------
# XET header parsing (unchanged contract — used for enrichment only)
# ---------------------------------------------------------------------------

@dataclass
class XetHeader:
    mips: int
    width: int
    height: int
    format: int
    first_surface_offset: int


def parse_xet_header(raw: bytes) -> XetHeader:
    if len(raw) < 0x14:
        raise ArcError(f"XET payload too short: {len(raw)}")
    if raw[:4] != b"\0XET":
        raise ArcError("not an XET payload")
    tex_flags = struct.unpack_from(">I", raw, 0x08)[0]
    mips = tex_flags & 0x3F
    width = (tex_flags >> 6) & 0x1FFF
    height = (tex_flags >> 19) & 0x1FFF
    fmt = raw[0x0E]
    off = struct.unpack_from(">I", raw, 0x10)[0]
    if off < 20 or off > len(raw):
        raise ArcError(f"invalid XET first surface offset {off} for {len(raw)} bytes")
    return XetHeader(mips=mips, width=width, height=height,
                     format=fmt, first_surface_offset=off)


# ---------------------------------------------------------------------------
# Enrichment using safe_arc.parse_arc
# ---------------------------------------------------------------------------

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _entry_field(entry, name, default=None):
    """safe_arc entries may be dicts or objects; handle both."""
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def enrich_inventory(records: Sequence[InventoryRecord], root: str,
                     strict: bool = True) -> List[InventoryRecord]:
    if not root:
        return list(records)
    safe_arc = _import_safe_arc()

    cache: Dict[str, Tuple[str, List[Any]]] = {}
    for r in records:
        rel = r.outer_arc_path.replace("\\", os.sep).replace("/", os.sep)
        if rel.startswith(os.sep):
            rel = rel[1:]
        abs_arc = os.path.join(root, rel)
        if not os.path.exists(abs_arc):
            if strict:
                raise ArcError(f"ARC not found under root: {abs_arc}")
            continue

        if abs_arc not in cache:
            with open(abs_arc, "rb") as f:
                arc_bytes = f.read()
            arc_sha = _sha256(arc_bytes)
            entries = safe_arc.parse_arc(arc_bytes)
            cache[abs_arc] = (arc_sha, entries)

        arc_sha, entries = cache[abs_arc]

        if r.entry_index < 0 or r.entry_index >= len(entries):
            raise ArcError(f"entry index {r.entry_index} out of range for {abs_arc}")
        entry = entries[r.entry_index]

        e_name = _entry_field(entry, "name", "")
        e_type = _entry_field(entry, "type_hash", 0)
        e_stored = _entry_field(entry, "stored", None)
        e_raw = _entry_field(entry, "raw", None)

        if e_type != r.type_hash:
            raise ArcError(
                f"type hash mismatch for {abs_arc}#{r.entry_index}: "
                f"csv=0x{r.type_hash:08X} arc=0x{e_type:08X}")
        if ascii_lower(str(e_name)) != ascii_lower(r.internal_path):
            raise ArcError(
                f"path mismatch for {abs_arc}#{r.entry_index}: "
                f"csv={r.internal_path!r} arc={e_name!r}")
        if e_stored is None or e_raw is None:
            raise ArcError(f"safe_arc returned no bytes for {abs_arc}#{r.entry_index}")

        r.outer_arc_sha256 = arc_sha
        r.stored_sha256 = _sha256(bytes(e_stored))
        r.expanded_sha256 = _sha256(bytes(e_raw))
        r.raw_member_size = len(e_raw)
        r.stored_size = len(e_stored)
        r.expanded_size = len(e_raw)
        r.flags = int(_entry_field(entry, "flags", r.flags) or 0)
        r.extra["arc_codec"] = _entry_field(entry, "codec", None)
        warning = _entry_field(entry, "warning", None)
        if warning:
            r.extra["arc_warning"] = warning

        if r.type_hash == R_TEXTURE:
            xet = parse_xet_header(bytes(e_raw))
            r.width = xet.width
            r.height = xet.height
            r.mips = xet.mips
            r.format = xet.format
            r.xet_first_surface_offset = xet.first_surface_offset
            r.xet_shell_sha256 = _sha256(bytes(e_raw)[:xet.first_surface_offset])
    return list(records)


# ---------------------------------------------------------------------------
# Analysis / structural helpers
# ---------------------------------------------------------------------------

def structural_key(rec):
    if rec.type_hash == R_TEXTURE:
        if None in (rec.width, rec.height, rec.mips, rec.format):
            return None
        return ("tex", rec.width, rec.height, rec.mips, rec.format,
                rec.surface_count if rec.surface_count is not None else 1)
    return None


def structural_compat(a, b):
    if a.type_hash != b.type_hash:
        return "INCOMPATIBLE"
    if a.type_hash == R_TEXTURE:
        if None in (a.width, a.height, a.mips, a.format):
            return "UNKNOWN"
        if None in (b.width, b.height, b.mips, b.format):
            return "UNKNOWN"
        if (a.width, a.height, a.mips, a.format) != (b.width, b.height, b.mips, b.format):
            return "INCOMPATIBLE"
        if a.surface_count and b.surface_count and a.surface_count != b.surface_count:
            return "INCOMPATIBLE"
        return "FULL"
    return "TYPE_ONLY"


def content_signature(rec):
    if rec.expanded_sha256:
        return ("expanded", rec.expanded_sha256)
    if rec.stored_sha256:
        return ("stored", rec.stored_sha256)
    return None


def payload_relation(a, b):
    if a.expanded_sha256 and b.expanded_sha256:
        if a.expanded_sha256 == b.expanded_sha256:
            return "EXACT_EXPANDED_MATCH"
        if structural_compat(a, b) == "FULL":
            return "SAME_STRUCTURE_DIFFERENT_CONTENT"
        return "DIFFERENT_CONTENT"
    if a.expanded_sha256 or b.expanded_sha256:
        return "UNKNOWN_COMPRESSION"
    if a.stored_sha256 and b.stored_sha256:
        return ("EXACT_STORED_MATCH" if a.stored_sha256 == b.stored_sha256
                else "DIFFERENT_CONTENT")
    return "UNKNOWN_COMPRESSION"


def donor_identity(rec):
    return (rec.game, rec.outer_arc_path, rec.entry_index, rec.type_hash,
            ascii_lower(rec.internal_path))


class Inventory:
    def __init__(self, records):
        self.records = sorted(records, key=lambda r: (
            r.outer_arc_path, r.entry_index, ascii_lower(r.internal_path)))
        self.by_type_path = defaultdict(list)
        self.by_expanded_sha = defaultdict(list)
        self.by_decoded_tex_sha = defaultdict(list)
        self.by_type_struct = defaultdict(list)
        self.by_type_skel = defaultdict(list)
        for r in self.records:
            self.by_type_path[(r.type_hash, r.runtime_key[1])].append(r)
            if r.expanded_sha256:
                self.by_expanded_sha[r.expanded_sha256].append(r)
            if r.decoded_texture_sha256:
                self.by_decoded_tex_sha[r.decoded_texture_sha256].append(r)
            sk = structural_key(r)
            if sk is not None:
                self.by_type_struct[(r.type_hash, sk)].append(r)
            self.by_type_skel[(r.type_hash, locale_skeleton(r.internal_path))].append(r)
        for d in (self.by_type_path, self.by_expanded_sha, self.by_decoded_tex_sha,
                  self.by_type_struct, self.by_type_skel):
            for k in d:
                d[k].sort(key=lambda r: (r.outer_arc_path, r.entry_index,
                                         ascii_lower(r.internal_path)))


def _mk_match(target, donor, cls, evidence, bridge_path=None):
    sc = structural_compat(target, donor)
    pr = payload_relation(target, donor)
    w = []
    if sc == "INCOMPATIBLE":
        w.append("structural_incompatibility")
    if sc == "UNKNOWN":
        w.append("structure_unknown")
    if pr == "UNKNOWN_COMPRESSION":
        w.append("payload_unresolved_compression")
    return Match(target=target, donor=donor, class_=cls,
                 evidence=list(evidence) + [
                     {"kind": "structural_compat", "value": sc},
                     {"kind": "payload_relation", "value": pr}],
                 structural_compat=sc, payload_relation=pr,
                 warnings=w, bridge_path=bridge_path)


def find_direct_candidates(target, donor_inv, allow_fuzzy):
    out = {}

    def add(m):
        k = donor_identity(m.donor)
        if k in out:
            out[k].evidence.extend(m.evidence)
        else:
            out[k] = m

    for d in donor_inv.by_type_path.get((target.type_hash, target.runtime_key[1]), []):
        if d is target:
            continue
        add(_mk_match(target, d, "EXACT", [
            {"kind": "exact_path", "path": target.internal_path,
             "type_hash": f"0x{target.type_hash:08X}"}]))

    if target.expanded_sha256:
        for d in donor_inv.by_expanded_sha.get(target.expanded_sha256, []):
            if d.type_hash != target.type_hash:
                continue
            if d.runtime_key == target.runtime_key:
                continue
            add(_mk_match(target, d, "CONTENT", [
                {"kind": "expanded_sha256_equal", "value": target.expanded_sha256}]))

    if target.decoded_texture_sha256:
        for d in donor_inv.by_decoded_tex_sha.get(target.decoded_texture_sha256, []):
            if d.type_hash != target.type_hash:
                continue
            if d.runtime_key == target.runtime_key:
                continue
            add(_mk_match(target, d, "CONTENT", [
                {"kind": "decoded_texture_sha256_equal",
                 "value": target.decoded_texture_sha256}]))

    t_skel = locale_skeleton(target.internal_path)
    for d in donor_inv.by_type_skel.get((target.type_hash, t_skel), []):
        if d.runtime_key == target.runtime_key:
            continue
        add(_mk_match(target, d, "LOCALE", [
            {"kind": "locale_skeleton_match",
             "target_path": target.internal_path,
             "donor_path": d.internal_path, "skeleton": t_skel}]))

    if allow_fuzzy:
        sk = structural_key(target)
        if sk is not None:
            for d in donor_inv.by_type_struct.get((target.type_hash, sk), []):
                if d.runtime_key == target.runtime_key:
                    continue
                add(_mk_match(target, d, "FUZZY_STRUCTURE", [
                    {"kind": "same_structural_key", "value": list(sk)}]))

    return sorted(out.values(), key=lambda m: (
        m.donor.outer_arc_path, m.donor.entry_index, ascii_lower(m.donor.internal_path)))


def _content_identity_matches(src, inv):
    out = []
    seen = set()

    def emit(rec, ev):
        k = donor_identity(rec)
        if k in seen:
            return
        seen.add(k)
        out.append((rec, ev))

    if src.expanded_sha256:
        for r in inv.by_expanded_sha.get(src.expanded_sha256, []):
            if r.type_hash != src.type_hash:
                continue
            emit(r, {"kind": "expanded_sha256_equal", "value": src.expanded_sha256})
    if src.decoded_texture_sha256:
        for r in inv.by_decoded_tex_sha.get(src.decoded_texture_sha256, []):
            if r.type_hash != src.type_hash:
                continue
            emit(r, {"kind": "decoded_texture_sha256_equal",
                     "value": src.decoded_texture_sha256})
    out.sort(key=lambda t: (t[0].outer_arc_path, t[0].entry_index))
    return out


def _sh_en_counterparts(jpn_node, sh_en_inv):
    seen = set()
    out = []

    def add(rec):
        k = donor_identity(rec)
        if k in seen:
            return
        seen.add(k)
        out.append(rec)

    skel = locale_skeleton(jpn_node.internal_path)
    for d in sh_en_inv.by_type_skel.get((jpn_node.type_hash, skel), []):
        add(d)
    for d in sh_en_inv.by_type_path.get((jpn_node.type_hash, jpn_node.runtime_key[1]), []):
        add(d)
    if jpn_node.expanded_sha256:
        for d in sh_en_inv.by_expanded_sha.get(jpn_node.expanded_sha256, []):
            if d.type_hash == jpn_node.type_hash:
                add(d)
    if jpn_node.decoded_texture_sha256:
        for d in sh_en_inv.by_decoded_tex_sha.get(jpn_node.decoded_texture_sha256, []):
            if d.type_hash == jpn_node.type_hash:
                add(d)
    out.sort(key=lambda r: (r.outer_arc_path, r.entry_index,
                            ascii_lower(r.internal_path)))
    return out


def find_bridge_matches(target, bridge_chain, sh_en_inv):
    if not bridge_chain:
        return []
    frontier = [(target, [])]
    for inv in bridge_chain:
        nxt = []
        for node, ev in frontier:
            for rec, rev in _content_identity_matches(node, inv):
                nxt.append((rec, ev + [dict(rev, step_game=rec.game,
                                            step_path=rec.internal_path)]))
        if not nxt:
            return []
        frontier = nxt
    out = {}
    for jpn_node, ev in frontier:
        for d in _sh_en_counterparts(jpn_node, sh_en_inv):
            k = donor_identity(d)
            bridge_path = ev + [{"kind": "sh_en_counterpart",
                                 "jpn_path": jpn_node.internal_path,
                                 "en_path": d.internal_path}]
            m = _mk_match(target, d, "JAPANESE_BRIDGE",
                          [{"kind": "japanese_bridge", "steps": len(ev),
                            "final_jpn_path": jpn_node.internal_path}],
                          bridge_path=bridge_path)
            if k in out:
                out[k].evidence.extend(m.evidence)
            else:
                out[k] = m
    return sorted(out.values(), key=lambda m: (
        m.donor.outer_arc_path, m.donor.entry_index,
        ascii_lower(m.donor.internal_path)))


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

def _candidate_class_ok(m, target, cfg):
    if m.structural_compat == "INCOMPATIBLE":
        return False, "structural_incompatible"
    if m.payload_relation == "EXACT_EXPANDED_MATCH":
        return True, "expanded_content_identity"
    if (m.payload_relation == "EXACT_STORED_MATCH"
            and not target.expanded_sha256 and not m.donor.expanded_sha256):
        return True, "stored_content_identity"
    if m.class_ == "EXACT":
        if target.type_hash not in VALIDATED_CLASSES:
            return False, "no_class_validator"
        if m.structural_compat != "FULL":
            return False, f"structural_{m.structural_compat.lower()}"
        return True, "texture_structural_match"
    if m.class_ == "JAPANESE_BRIDGE":
        if target.type_hash not in VALIDATED_CLASSES:
            return False, "no_class_validator"
        if m.structural_compat != "FULL":
            return False, f"structural_{m.structural_compat.lower()}"
        return True, "japanese_bridge"
    if m.class_ == "LOCALE":
        return False, "locale_only_not_safe"
    if m.class_ == "CONTENT":
        return True, "content_identity"
    return False, "unknown_class"


def decide(target, matches, cfg):
    warnings = []
    safe_by_class = defaultdict(list)
    for m in matches:
        ok, _ = _candidate_class_ok(m, target, cfg)
        if ok:
            safe_by_class[m.class_].append(m)
    for cls in ("EXACT", "JAPANESE_BRIDGE", "CONTENT"):
        candidates = safe_by_class.get(cls, [])
        if not candidates:
            continue
        by_donor = {}
        for m in candidates:
            k = donor_identity(m.donor)
            if k not in by_donor:
                by_donor[k] = m
        unique = sorted(by_donor.values(), key=lambda m: (
            m.donor.outer_arc_path, m.donor.entry_index,
            ascii_lower(m.donor.internal_path)))
        by_sig = defaultdict(list)
        for m in unique:
            by_sig[content_signature(m.donor)].append(m)
        decision = "EXACT_SAFE_DONOR" if cls == "EXACT" else "STRONG_SAFE_DONOR"
        if len(by_sig) == 1:
            return decision, unique[0], warnings
        t_sig = content_signature(target)
        if t_sig and t_sig in by_sig:
            chosen = min(by_sig[t_sig], key=lambda m: (
                m.donor.outer_arc_path, m.donor.entry_index))
            return decision, chosen, warnings
        warnings.append(f"ambiguous_{cls.lower()}_donors")
        return "REVIEW_REQUIRED", None, warnings
    if matches:
        if any(m.class_ == "LOCALE" for m in matches):
            warnings.append("locale_only_requires_bridge_or_content")
            return "REVIEW_REQUIRED", None, warnings
        if any(m.class_ == "FUZZY_STRUCTURE" for m in matches):
            warnings.append("fuzzy_only_no_plan")
            return "REVIEW_REQUIRED", None, warnings
        warnings.append("candidates_present_but_not_auto_writable")
        return "REVIEW_REQUIRED", None, warnings
    return "NO_DONOR", None, warnings


def resolve_target(target, sh_en_inv, bridge_chain, cfg):
    direct = find_direct_candidates(target, sh_en_inv, cfg.allow_fuzzy)
    bridge = find_bridge_matches(target, bridge_chain, sh_en_inv)
    decision, selected, warns = decide(target, direct + bridge, cfg)
    return Resolution(target=target, direct_matches=direct, bridge_matches=bridge,
                      decision=decision, selected=selected, warnings=warns)


# ---------------------------------------------------------------------------
# Providers / evidence
# ---------------------------------------------------------------------------

def load_effective_provider_evidence(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for k, v in data.items():
        if "|" not in k:
            continue
        th_str, path_part = k.split("|", 1)
        th = _parse_int(th_str)
        if th is None:
            continue
        key = f"0x{th:08X}|{normalize_path_for_evidence(path_part)}"
        out[key] = EffectiveProviderEvidence(
            effective_arc=str(v["effective_arc"]),
            effective_index=int(v["effective_index"]),
            evidence=str(v.get("evidence", "")))
    return out


def provider_evidence_key(rk):
    return f"0x{rk[0]:08X}|{normalize_path_for_evidence(rk[1])}"


def _find_provider_by_evidence(providers, ev):
    ev_arc = normalize_path_for_evidence(ev.effective_arc)
    for p in providers:
        if (normalize_path_for_evidence(p.outer_arc_path) == ev_arc
                and p.entry_index == ev.effective_index):
            return p
    return None


def analyse_providers(target, providers):
    runtime_key = target.runtime_key
    exact = sorted([r for r in providers if r.runtime_key == runtime_key],
                   key=lambda r: (r.outer_arc_path, r.entry_index))
    skel = locale_skeleton(target.internal_path)
    exact_ids = {(r.outer_arc_path, r.entry_index) for r in exact}
    analysis_equiv = sorted(
        [r for r in providers
         if (r.outer_arc_path, r.entry_index) not in exact_ids
         and r.type_hash == target.type_hash
         and locale_skeleton(r.internal_path) == skel],
        key=lambda r: (r.outer_arc_path, r.entry_index))
    sig_groups = defaultdict(list)
    for r in exact:
        sig_groups[content_signature(r)].append(r)
    if len(sig_groups) > 1:
        policy = "REVIEW_PROVIDER_ORDER"
    elif len(exact) > 1:
        policy = "SAFE_IDENTICAL_PROVIDERS"
    else:
        policy = "PATCH_EFFECTIVE_ONLY"
    return {
        "runtime_key": [runtime_key[0], runtime_key[1]],
        "exact_runtime_providers": [
            {"arc": r.outer_arc_path, "index": r.entry_index,
             "path": r.internal_path, "content_signature": content_signature(r)}
            for r in exact],
        "analysis_equivalence": [
            {"arc": r.outer_arc_path, "index": r.entry_index,
             "path": r.internal_path, "content_signature": content_signature(r)}
            for r in analysis_equiv],
        "distinct_payload_signatures": len(sig_groups),
        "recommended_policy": policy,
    }


# ---------------------------------------------------------------------------
# Path rebasing
# ---------------------------------------------------------------------------

def _safe_relative(path):
    if not path:
        raise ValueError("empty path")
    if re.match(r"^[A-Za-z]:", path):
        raise ValueError(f"absolute drive path rejected: {path}")
    if path.startswith("\\") or path.startswith("/"):
        raise ValueError(f"absolute path rejected: {path}")
    parts = [p for p in re.split(r"[\\/]+", path) if p]
    if not parts:
        raise ValueError(f"empty path after split: {path}")
    for p in parts:
        if p == "..":
            raise ValueError(f"parent-escape rejected: {path}")
    return "\\".join(parts)


def rebase_for_harness(cfg, arc_path, side):
    rel = _safe_relative(arc_path)
    prefix = cfg.utage_prefix if side == "target" else cfg.sh_prefix
    if prefix:
        return _safe_relative(prefix) + "\\" + rel
    return rel


# ---------------------------------------------------------------------------
# Harness eligibility / builders
# ---------------------------------------------------------------------------

def xet_shell_compatible(target, donor):
    if target.raw_member_size is None or donor.raw_member_size is None:
        return False, "missing_raw_member_size"
    if target.raw_member_size != donor.raw_member_size:
        return False, "raw_member_size_mismatch"
    if target.raw_member_size < 20:
        return False, "raw_member_size_too_small"
    if target.xet_first_surface_offset is None or donor.xet_first_surface_offset is None:
        return False, "missing_surface_offset"
    if target.xet_first_surface_offset != donor.xet_first_surface_offset:
        return False, "surface_offset_mismatch"
    if target.xet_shell_sha256 is None or donor.xet_shell_sha256 is None:
        return False, "missing_shell_sha256"
    if target.xet_shell_sha256 != donor.xet_shell_sha256:
        return False, "shell_sha256_mismatch"
    return True, "ok"


def harness_ready_eligible(target, donor):
    if target.harness_key != donor.harness_key:
        return False, "harness_key_mismatch"
    if not target.expanded_sha256:
        return False, "target_missing_expanded_sha256"
    if not donor.expanded_sha256:
        return False, "donor_missing_expanded_sha256"
    if not target.outer_arc_sha256:
        return False, "target_missing_outer_arc_sha256"
    if not donor.outer_arc_sha256:
        return False, "donor_missing_outer_arc_sha256"
    if target.type_hash == R_TEXTURE:
        ok, reason = xet_shell_compatible(target, donor)
        if not ok:
            return False, reason
    return True, "ok"


def key_diff_reason(target, donor):
    if target.type_hash != donor.type_hash:
        return "type_hash_mismatch"
    if ascii_lower(target.internal_path) == ascii_lower(donor.internal_path):
        return "separator_mismatch"
    if locale_skeleton(target.internal_path) == locale_skeleton(donor.internal_path):
        return "locale_segment_differs"
    return "internal_path_moved_or_renamed"


def build_harness_change(target, donor, cfg):
    assert target.expanded_sha256 and donor.expanded_sha256
    assert target.outer_arc_sha256 and donor.outer_arc_sha256
    return HarnessChange(
        arc=rebase_for_harness(cfg, target.outer_arc_path, "target"),
        index=target.entry_index,
        name=target.internal_path,
        type_hash=target.type_hash,
        expected_raw_sha256=target.expanded_sha256,
        source_arc_sha256=target.outer_arc_sha256,
        donor_arc=rebase_for_harness(cfg, donor.outer_arc_path, "donor"),
        donor_index=donor.entry_index,
        donor_raw_sha256=donor.expanded_sha256,
        donor_source_sha256=donor.outer_arc_sha256,
    )


def build_graft_candidate(provider, match, resolution, eligibility_reason):
    t = provider
    d = match.donor
    return GraftCandidate(
        target_arc=t.outer_arc_path, target_index=t.entry_index,
        target_path=t.internal_path, target_type_hash=t.type_hash,
        target_stored_sha256=t.stored_sha256,
        target_expanded_sha256=t.expanded_sha256,
        target_raw_member_size=t.raw_member_size,        target_xet_first_surface_offset=t.xet_first_surface_offset,
        target_xet_shell_sha256=t.xet_shell_sha256,
        target_width=t.width, target_height=t.height,
        target_mips=t.mips, target_format=t.format,
        donor_arc=d.outer_arc_path, donor_index=d.entry_index,
        donor_path=d.internal_path, donor_type_hash=d.type_hash,
        donor_stored_sha256=d.stored_sha256,
        donor_expanded_sha256=d.expanded_sha256,
        donor_raw_member_size=d.raw_member_size,
        donor_xet_first_surface_offset=d.xet_first_surface_offset,
        donor_xet_shell_sha256=d.xet_shell_sha256,
        donor_width=d.width, donor_height=d.height,
        donor_mips=d.mips, donor_format=d.format,
        match_class=match.class_,
        confidence_level=match.confidence_level,
        structural_compatibility=match.structural_compat,
        payload_relation=match.payload_relation,
        harness_eligibility_failure=eligibility_reason,
        key_difference=key_diff_reason(t, d),
        required_operation=(
            "transplant compatible PAYLOAD into TARGET resource shell; "
            "preserve target member identity (path, type_hash, header metadata)"),
        evidence=match.evidence,
        bridge_path=match.bridge_path,
        provider_analysis=resolution.provider_analysis,
        provider_status=resolution.provider_status,
        warnings=list(match.warnings) + list(resolution.warnings)
                 + list(resolution.provider_messages),
    )


# ---------------------------------------------------------------------------
# Group resolution
# ---------------------------------------------------------------------------

@dataclass
class ProviderAction:
    provider: InventoryRecord
    match: Match
    kind: str
    reason: str


@dataclass
class GroupDecision:
    resolution: Resolution
    actions: List[ProviderAction] = field(default_factory=list)


def resolve_group(providers, sh_en_inv, bridge_chain, cfg, evidence_map):
    providers = sorted(providers, key=lambda r: (r.outer_arc_path, r.entry_index))
    rep = providers[0]
    res = resolve_target(rep, sh_en_inv, bridge_chain, cfg)
    res.provider_analysis = analyse_providers(rep, providers)
    gd = GroupDecision(resolution=res)
    if res.decision not in ("EXACT_SAFE_DONOR", "STRONG_SAFE_DONOR") or not res.selected:
        res.provider_status = res.decision
        return gd
    donor = res.selected.donor
    n = len(providers)
    sigs = {content_signature(p) for p in providers}

    def try_emit(provider):
        ok, reason = harness_ready_eligible(provider, donor)
        gd.actions.append(ProviderAction(provider, res.selected,
                                         "HARNESS" if ok else "GRAFT", reason))

    if n == 1:
        try_emit(providers[0])
        res.provider_status = ("EMIT_SINGLE" if gd.actions and gd.actions[0].kind == "HARNESS"
                               else "EMIT_GRAFT_SINGLE")
        return gd

    if len(sigs) == 1:
        ev = evidence_map.get(provider_evidence_key(rep.runtime_key))
        if cfg.duplicate_policy == "SYNC_EXACT_PROVIDERS":
            reasons = []
            for p in providers:
                ok, reason = harness_ready_eligible(p, donor)
                if not ok:
                    reasons.append(f"{p.outer_arc_path}#{p.entry_index}:{reason}")
            if reasons:
                res.provider_status = "REVIEW_INCOMPATIBLE_SIBLING"
                res.provider_messages.extend(reasons)
                return gd
            for p in providers:
                gd.actions.append(ProviderAction(p, res.selected, "HARNESS", "ok"))
            res.provider_status = "EMIT_SYNC"
            return gd
        if ev:
            eff = _find_provider_by_evidence(providers, ev)
            if eff is None:
                res.provider_status = "REVIEW_EVIDENCE_MISMATCH"
                res.provider_messages.append(
                    "effective-provider evidence does not match any provider")
                return gd
            try_emit(eff)
            if gd.actions and gd.actions[0].kind == "HARNESS":
                res.provider_status = "EMIT_EFFECTIVE_PROVIDER"
            else:
                res.provider_status = "REVIEW_EFFECTIVE_INELIGIBLE"
                res.provider_messages.append(gd.actions[0].reason)
                gd.actions.clear()
            return gd
        res.provider_status = "PROVIDER_SELECTION_REQUIRED"
        res.provider_messages.append(
            "multiple identical providers; no effective-provider evidence")
        return gd

    ev = evidence_map.get(provider_evidence_key(rep.runtime_key))
    if ev:
        eff = _find_provider_by_evidence(providers, ev)
        if eff is None:
            res.provider_status = "REVIEW_EVIDENCE_MISMATCH"
            res.provider_messages.append(
                "effective-provider evidence does not match any provider")
            return gd
        try_emit(eff)
        if gd.actions and gd.actions[0].kind == "HARNESS":
            res.provider_status = "EMIT_EFFECTIVE_PROVIDER"
        else:
            res.provider_status = "REVIEW_EFFECTIVE_INELIGIBLE"
            res.provider_messages.append(gd.actions[0].reason)
            gd.actions.clear()
        return gd
    res.provider_status = "REVIEW_PROVIDER_ORDER"
    res.provider_messages.append(
        "divergent exact providers; no effective-provider evidence")
    return gd


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _record_to_dict(r):
    return {
        "game": r.game, "outer_arc_path": r.outer_arc_path,
        "entry_index": r.entry_index,
        "type_hash": f"0x{r.type_hash:08X}",
        "internal_path": r.internal_path,
        "stored_sha256": r.stored_sha256,
        "expanded_sha256": r.expanded_sha256,
        "decoded_texture_sha256": r.decoded_texture_sha256,
        "width": r.width, "height": r.height, "mips": r.mips,
        "format": None if r.format is None else f"0x{r.format:02X}",
        "outer_arc_sha256": r.outer_arc_sha256,
        "raw_member_size": r.raw_member_size,
        "xet_first_surface_offset": r.xet_first_surface_offset,
        "xet_shell_sha256": r.xet_shell_sha256,
    }


def _match_to_dict(m):
    return {
        "donor_game": m.donor.game,
        "donor_outer_arc": m.donor.outer_arc_path,
        "donor_internal_path": m.donor.internal_path,
        "match_class": m.class_,
        "confidence_level": m.confidence_level,
        "structural_compatibility": m.structural_compat,
        "payload_relation": m.payload_relation,
        "evidence": m.evidence, "japanese_bridge": m.bridge_path,
        "warnings": m.warnings,
    }


def _resolution_to_dict(r):
    return {
        "target": _record_to_dict(r.target),
        "donor_candidates": sorted(
            [_match_to_dict(m) for m in r.direct_matches + r.bridge_matches],
            key=lambda x: (x["donor_outer_arc"], x["donor_internal_path"])),
        "decision": r.decision,
        "selected": _match_to_dict(r.selected) if r.selected else None,
        "warnings": r.warnings,
        "provider_analysis": r.provider_analysis,
        "provider_status": r.provider_status,
        "provider_messages": r.provider_messages,
    }


def write_report(resolutions, out_path):
    resolutions = sorted(resolutions, key=lambda r: (
        r.target.outer_arc_path, r.target.entry_index,
        ascii_lower(r.target.internal_path)))
    payload = {"version": 5, "kind": "utage_donor_report",
               "records": [_resolution_to_dict(r) for r in resolutions]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def write_harness_plan(cfg, changes, out_path):
    changes_sorted = sorted(changes, key=lambda c: (c.arc, c.index, c.name))
    payload = {"root": cfg.harness_root,
               "changes": [asdict(c) for c in changes_sorted]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def write_graft_candidates(cands, out_path):
    cands_sorted = sorted(cands, key=lambda g: (
        g.target_arc, g.target_index, g.target_path))
    payload = {"version": 5, "kind": "utage_payload_graft_candidates",
               "candidates": [asdict(c) for c in cands_sorted]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(cfg, utage_path, sh_en_path, bridge_paths,
                 report_path, harness_path, graft_path, input_format="auto"):
    utage_records = load_inventory_smart(utage_path, input_format, "UTAGE_LIVE")
    sh_en_records = load_inventory_smart(sh_en_path, input_format, "SH_EN")
    bridge_chain = [Inventory(load_inventory_smart(p, input_format, g))
                    for g, p in bridge_paths]

    if cfg.utage_root:
        utage_records = enrich_inventory(utage_records, cfg.utage_root)
    if cfg.sh_root:
        sh_en_records = enrich_inventory(sh_en_records, cfg.sh_root)

    sh_en_inv = Inventory(sh_en_records)
    evidence_map = load_effective_provider_evidence(cfg.effective_provider_evidence_path)

    groups = defaultdict(list)
    for r in utage_records:
        groups[r.runtime_key].append(r)

    resolutions = []
    all_changes = []
    all_grafts = []
    seen_change_keys = set()

    for rk in sorted(groups.keys()):
        providers = groups[rk]
        gd = resolve_group(providers, sh_en_inv, bridge_chain, cfg, evidence_map)
        resolutions.append(gd.resolution)
        for act in gd.actions:
            if act.kind == "HARNESS":
                ch = build_harness_change(act.provider, act.match.donor, cfg)
                key = (ch.arc, ch.index, ch.name, ch.type_hash)
                if key in seen_change_keys:
                    continue
                seen_change_keys.add(key)
                all_changes.append(ch)
            else:
                all_grafts.append(build_graft_candidate(
                    act.provider, act.match, gd.resolution, act.reason))

    write_report(resolutions, report_path)
    write_harness_plan(cfg, all_changes, harness_path)
    write_graft_candidates(all_grafts, graft_path)

    summary = {"targets": len(resolutions),
               "harness_ready_changes": len(all_changes),
               "graft_candidates": len(all_grafts),
               "by_decision": {}, "by_provider_status": {}}
    for r in resolutions:
        summary["by_decision"][r.decision] = \
            summary["by_decision"].get(r.decision, 0) + 1
        if r.provider_status:
            summary["by_provider_status"][r.provider_status] = \
                summary["by_provider_status"].get(r.provider_status, 0) + 1
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _smoke_arc(arc_path: str, limit: int = 5) -> int:
    safe_arc = _import_safe_arc()
    with open(arc_path, "rb") as f:
        arc_bytes = f.read()
    print(f"# file: {arc_path}")
    print(f"# size: {len(arc_bytes)}")
    print(f"# sha256: {_sha256(arc_bytes)}")
    entries = safe_arc.parse_arc(arc_bytes)
    print(f"# entries: {len(entries)}")
    for i, e in enumerate(entries[:limit]):
        name = _entry_field(e, "name", "?")
        th = _entry_field(e, "type_hash", 0)
        ss = _entry_field(e, "compressed_size", 0)
        rs = _entry_field(e, "raw_size", 0)
        fl = _entry_field(e, "flags", 0)
        off = _entry_field(e, "payload_offset", 0)
        codec = _entry_field(e, "codec", "?")
        warn = _entry_field(e, "warning", None)
        print(f"  [{i}] name={name!r} type=0x{th:08X} "
              f"stored={ss} raw={rs} flags={fl} off={off} codec={codec}"
              + (f" warning={warn!r}" if warn else ""))
    return 0


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Utage -> Samurai Heroes donor matcher V5")
    ap.add_argument("--smoke-arc", default="",
                    help="Parse a real ARC via safe_arc and print first entries. Exits.")
    ap.add_argument("--smoke-limit", type=int, default=5)
    ap.add_argument("--utage")
    ap.add_argument("--sh-en")
    ap.add_argument("--bridge", action="append", default=[])
    ap.add_argument("--report", default="")
    ap.add_argument("--harness-plan", default="")
    ap.add_argument("--graft-plan", default="")
    ap.add_argument("--harness-root", default="")
    ap.add_argument("--utage-prefix", default="")
    ap.add_argument("--sh-prefix", default="")
    ap.add_argument("--utage-root", default="")
    ap.add_argument("--sh-root", default="")
    ap.add_argument("--provider-evidence", default="")
    ap.add_argument("--allow-fuzzy", action="store_true")
    ap.add_argument("--duplicate-policy",
                    choices=["REPORT_ONLY", "SYNC_EXACT_PROVIDERS"],
                    default="REPORT_ONLY")
    ap.add_argument("--input-format", choices=["auto", "foundry", "generic"],
                    default="auto")
    args = ap.parse_args(argv)

    if args.smoke_arc:
        return _smoke_arc(args.smoke_arc, args.smoke_limit)

    for req in ("utage", "sh_en", "report", "harness_plan", "graft_plan"):
        if not getattr(args, req):
            ap.error(f"--{req.replace('_', '-')} is required")

    bridge = []
    for spec in args.bridge:
        if ":" not in spec:
            ap.error(f"--bridge expects GAMENAME:PATH, got {spec!r}")
        g, p = spec.split(":", 1)
        bridge.append((g, p))

    cfg = Config(harness_root=args.harness_root,
                 utage_prefix=args.utage_prefix, sh_prefix=args.sh_prefix,
                 utage_root=args.utage_root, sh_root=args.sh_root,
                 effective_provider_evidence_path=args.provider_evidence,
                 allow_fuzzy=args.allow_fuzzy,
                 duplicate_policy=args.duplicate_policy)
    summary = run_pipeline(cfg, args.utage, args.sh_en, bridge,
                           args.report, args.harness_plan, args.graft_plan,
                           input_format=args.input_format)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())