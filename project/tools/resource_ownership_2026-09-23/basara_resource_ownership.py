#!/usr/bin/env python3
"""
BASARA Foundry Resource Ownership / Precedence Analyzer
2026-09-23

Production purpose:
  Scan an Utage ARC tree and answer:
    TYPE + exact canonical internal path
      -> every provider ARC
      -> payload identity/divergence
      -> provider order (when supplied)
      -> likely first successful population claim
      -> patch/synchronisation risk

Grounded in the 2026-09-23 Utage RE findings:
  * ARC v8 entry stride = 0x50.
  * entry+0x40 = raw resource type hash.
  * exact runtime path identity is ASCII-lowercased bytes, NUL-trimmed.
  * locale abstraction is analysis-only and NEVER used for exact runtime identity.
  * duplicate typed/path entries converge on a shared global ResourceObject.
  * first successful payload population claim wins among co-resident duplicates.
  * stored packing differences do not imply expanded-payload differences.
  * failed zlib decompression does NOT mean "raw/uncompressed".

Important limitation:
  Static directory order is NOT runtime registration order.
  Use --load-order or --rpcs3-log for effective-provider analysis.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path

LANGS = {b"jpn", b"eng", b"ger", b"fre", b"spa", b"ita", b"dut", b"kor", b"twn"}
ARC_MAGIC = b"\0CRA"
ARC_VERSION = 8
ENTRY_SIZE = 0x50

KNOWN_TYPES = {
    0x73850D05: "rArchive",
    0x241F5DEB: "rTexture",
    0x242BB29A: "rGUIMessage",
    0x2D462600: "rGUIFont",
    0x22948394: "rGUI",
    0x6450A37A: "rNameId",
    0x60DD1B16: "rLayoutParameter/.lsp",
}

OPEN_RE = re.compile(
    r"(?:Opening|opened|open(?:ing)?|File).*?(?:/dev_[^/\s]+/)?(?P<path>[^\r\n\"']+?\.arc)\b",
    re.IGNORECASE,
)

def ascii_lower(data: bytes) -> bytes:
    return bytes((b + 32) if 0x41 <= b <= 0x5A else b for b in data)

def exact_path(raw64: bytes) -> bytes:
    return ascii_lower(raw64.split(b"\0", 1)[0])

def locale_equiv(path: bytes) -> bytes:
    parts = path.split(b"\\")
    return b"\\".join(b"<LANG>" if p.lower() in LANGS else p for p in parts)

def display_bytes(b: bytes) -> str:
    return b.decode("latin1", errors="replace")

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def try_expand(stored: bytes, stored_size: int, expanded_size: int, flags: int):
    """
    Conservative fingerprinting.
    We only claim expanded bytes when we can validate the result.
    ARC flags are preserved in output; this function does not pretend every
    non-raw member is zlib.
    """
    # Strong raw case: byte count already equals target expanded size.
    if stored_size == expanded_size and len(stored) == expanded_size:
        return stored, "raw_size_match"

    # Known/common Utage path: zlib payload. Accept only exact expected size.
    try:
        out = zlib.decompress(stored)
        if len(out) == expanded_size:
            return out, "zlib_validated"
    except zlib.error:
        pass

    return None, "unresolved_compression"

def parse_arc(path: Path, root: Path):
    data = path.read_bytes()
    if len(data) < 8 or data[:4] != ARC_MAGIC:
        return None
    version, count = struct.unpack(">HH", data[4:8])
    if version != ARC_VERSION:
        return None

    table_end = 8 + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError(f"{path}: truncated ARC entry table")

    rel_arc = path.relative_to(root).as_posix()
    entries = []
    for i in range(count):
        off = 8 + i * ENTRY_SIZE
        raw_name = data[off:off+64].split(b"\0", 1)[0]
        type_hash, stored_size, packed, data_offset = struct.unpack(">IIII", data[off+64:off+80])
        expanded_size = packed >> 3
        flags = packed & 7

        if data_offset + stored_size > len(data):
            stored = data[data_offset:]
            bounds_ok = False
        else:
            stored = data[data_offset:data_offset+stored_size]
            bounds_ok = True

        expanded, method = try_expand(stored, stored_size, expanded_size, flags)
        expanded_sha = sha256(expanded) if expanded is not None else None

        entries.append({
            "arc": rel_arc,
            "index": i,
            "raw_path_hex": raw_name.hex(),
            "physical_path": display_bytes(raw_name),
            "exact_path": display_bytes(exact_path(raw_name)),
            "locale_equiv_path": display_bytes(locale_equiv(exact_path(raw_name))),
            "type_hash": type_hash,
            "type_hex": f"0x{type_hash:08X}",
            "type_name": KNOWN_TYPES.get(type_hash, ""),
            "stored_size": stored_size,
            "expanded_size": expanded_size,
            "flags": flags,
            "data_offset": data_offset,
            "bounds_ok": bounds_ok,
            "stored_sha256": sha256(stored),
            "expanded_sha256": expanded_sha,
            "decode_method": method,
        })
    return entries

def provider_variant(e):
    if e["expanded_sha256"]:
        return ("expanded", e["expanded_sha256"], e["expanded_size"])
    return (
        "raw_unresolved",
        e["stored_sha256"],
        e["flags"],
        e["stored_size"],
        e["expanded_size"],
    )

def classify_group(providers):
    variants = {provider_variant(e) for e in providers}
    unresolved = any(e["expanded_sha256"] is None for e in providers)

    if len(variants) == 1:
        if unresolved:
            # Identical raw/flags/sizes is safe identical even without decode.
            return "SAFE_IDENTICAL_RAW"
        return "SAFE_IDENTICAL_EXPANDED"

    if unresolved:
        return "UNRESOLVED_COMPRESSION"
    return "DIVERGENT"

def load_order_file(path: Path, root: Path):
    """
    One ARC per line, earliest registration first.
    Lines may be relative paths or basenames. # comments allowed.
    """
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip().replace("\\", "/")
        if line:
            out.append(line.lower())
    return out

def load_order_from_log(path: Path):
    """
    Best-effort extraction of ARC opens from an RPCS3 log.
    Repeated opens are retained in event order, then the first occurrence of
    each normalized path/basename is used as a static registration hint.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    events = []
    for line in text.splitlines():
        if ".arc" not in line.lower():
            continue
        # More permissive than OPEN_RE because RPCS3 log formatting varies.
        for m in re.finditer(r"(?P<p>(?:/dev_[^/\s]+/)?[A-Za-z0-9_./\\%-]+\.arc)", line, re.I):
            p = m.group("p").replace("\\", "/").lower()
            events.append(p)
    return events

def rank_provider(arc: str, order):
    if not order:
        return None
    a = arc.replace("\\", "/").lower()
    base = a.rsplit("/", 1)[-1]
    best = None
    for idx, item in enumerate(order):
        item = item.replace("\\", "/").lower()
        if a.endswith(item) or item.endswith(a) or item.rsplit("/", 1)[-1] == base:
            best = idx if best is None else min(best, idx)
    return best

def main():
    ap = argparse.ArgumentParser(
        description="BASARA Foundry Utage resource ownership / precedence analyzer"
    )
    ap.add_argument("root", type=Path, help="Root directory to recursively scan for *.arc")
    ap.add_argument("--out", type=Path, default=None, help="Output directory")
    ap.add_argument("--load-order", type=Path, help="Text file: ARC paths in earliest-registration-first order")
    ap.add_argument("--rpcs3-log", type=Path, help="RPCS3 log used to derive best-effort ARC open order")
    ap.add_argument("--query", help="Case-insensitive substring filter for path/type/ARC")
    args = ap.parse_args()

    root = args.root.resolve()
    outdir = (args.out or (root / "_BASARA_RESOURCE_ANALYSIS")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    order = []
    order_source = None
    if args.load_order:
        order = load_order_file(args.load_order, root)
        order_source = str(args.load_order)
    elif args.rpcs3_log:
        order = load_order_from_log(args.rpcs3_log)
        order_source = str(args.rpcs3_log)

    resources = []
    parse_errors = []
    arcs = []
    for p in sorted(root.rglob("*.arc")):
        try:
            parsed = parse_arc(p, root)
            if parsed is not None:
                arcs.append(p.relative_to(root).as_posix())
                resources.extend(parsed)
        except Exception as exc:
            parse_errors.append({"arc": str(p), "error": repr(exc)})

    exact = defaultdict(list)
    locale = defaultdict(list)
    for e in resources:
        exact[(e["type_hash"], e["exact_path"])].append(e)
        locale[(e["type_hash"], e["locale_equiv_path"])].append(e)

    groups = []
    for (type_hash, path), providers in exact.items():
        if len(providers) < 2:
            continue

        cls = classify_group(providers)
        ranked = []
        for e in providers:
            r = rank_provider(e["arc"], order)
            ranked.append((r, e))

        known = [(r, e) for r, e in ranked if r is not None]
        known.sort(key=lambda x: x[0])

        effective = known[0][1]["arc"] if known else None
        effective_rank = known[0][0] if known else None

        # We can only call it a precedence hazard when order evidence exists
        # and payloads are divergent.
        if cls == "DIVERGENT" and effective:
            risk = "DIVERGENT_EFFECTIVE_PROVIDER_KNOWN"
        elif cls == "DIVERGENT":
            risk = "DIVERGENT_ORDER_UNKNOWN"
        elif cls == "UNRESOLVED_COMPRESSION":
            risk = "UNRESOLVED_COMPRESSION"
        else:
            risk = "SAFE_IDENTICAL"

        groups.append({
            "type_hash": type_hash,
            "type_hex": f"0x{type_hash:08X}",
            "type_name": KNOWN_TYPES.get(type_hash, ""),
            "exact_path": path,
            "provider_count": len(providers),
            "classification": cls,
            "risk": risk,
            "effective_provider": effective,
            "effective_order_index": effective_rank,
            "providers": providers,
        })

    groups.sort(key=lambda g: (
        0 if g["classification"] == "DIVERGENT" else 1,
        g["type_hex"],
        g["exact_path"],
    ))

    # Locale-equivalence groups are intentionally separate and never drive
    # effective-provider claims.
    locale_groups = []
    for (type_hash, path), providers in locale.items():
        physical_exact = {(e["type_hash"], e["exact_path"]) for e in providers}
        if len(physical_exact) > 1:
            locale_groups.append({
                "type_hash": type_hash,
                "type_hex": f"0x{type_hash:08X}",
                "type_name": KNOWN_TYPES.get(type_hash, ""),
                "locale_equiv_path": path,
                "provider_count": len(providers),
                "exact_identity_count": len(physical_exact),
                "providers": providers,
            })

    q = (args.query or "").lower()
    if q:
        def matches(g):
            hay = " ".join([
                g.get("type_hex",""), g.get("type_name",""), g.get("exact_path",""),
                " ".join(p["arc"] for p in g.get("providers",[]))
            ]).lower()
            return q in hay
        query_groups = [g for g in groups if matches(g)]
    else:
        query_groups = groups

    summary = {
        "format": "BASARA_FOUNDRY_RESOURCE_OWNERSHIP_V1",
        "root": str(root),
        "arc_count": len(arcs),
        "resource_count": len(resources),
        "exact_duplicate_class_count": len(groups),
        "safe_identical_expanded": sum(g["classification"] == "SAFE_IDENTICAL_EXPANDED" for g in groups),
        "safe_identical_raw": sum(g["classification"] == "SAFE_IDENTICAL_RAW" for g in groups),
        "divergent_exact_duplicate_classes": sum(g["classification"] == "DIVERGENT" for g in groups),
        "unresolved_compression_classes": sum(g["classification"] == "UNRESOLVED_COMPRESSION" for g in groups),
        "locale_equivalence_class_count": len(locale_groups),
        "load_order_source": order_source,
        "load_order_event_count": len(order),
        "parse_error_count": len(parse_errors),
        "precedence_model": "first successful payload population claim wins among co-resident exact typed/path duplicates",
        "warning": "effective_provider is only emitted when load-order evidence matches a provider; static filesystem order is never treated as runtime precedence",
    }

    def compact_provider(e):
        return {k: e[k] for k in (
            "arc","index","physical_path","exact_path","type_hex","type_name",
            "stored_size","expanded_size","flags","data_offset",
            "stored_sha256","expanded_sha256","decode_method","bounds_ok"
        )}

    report = {
        "summary": summary,
        "parse_errors": parse_errors,
        "exact_duplicate_classes": [
            {**{k:v for k,v in g.items() if k != "providers"},
             "providers":[compact_provider(e) for e in g["providers"]]}
            for g in groups
        ],
        "locale_equivalence_classes": [
            {**{k:v for k,v in g.items() if k != "providers"},
             "providers":[compact_provider(e) for e in g["providers"]]}
            for g in locale_groups
        ],
    }

    (outdir / "resource_ownership.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    with (outdir / "resources.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "arc","index","physical_path","exact_path","locale_equiv_path",
            "type_hex","type_name","stored_size","expanded_size","flags",
            "data_offset","stored_sha256","expanded_sha256","decode_method","bounds_ok"
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(resources)

    with (outdir / "duplicate_classes.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "type_hex","type_name","exact_path","provider_count","classification",
            "risk","effective_provider","effective_order_index","providers"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for g in groups:
            w.writerow({
                **{k:g.get(k) for k in fields if k != "providers"},
                "providers":" | ".join(e["arc"] for e in g["providers"])
            })

    # Human-readable priority report.
    lines = [
        "# BASARA Foundry Resource Ownership / Precedence Report",
        "",
        "## Summary",
        "",
        *(f"- **{k}:** {v}" for k,v in summary.items()),
        "",
        "## Divergent / unresolved exact duplicate classes",
        "",
    ]
    hazards = [g for g in query_groups if g["classification"] in ("DIVERGENT","UNRESOLVED_COMPRESSION")]
    if not hazards:
        lines.append("None in the selected query.")
    for g in hazards:
        lines += [
            f"### {g['type_hex']} {g['type_name']} — `{g['exact_path']}`",
            f"- Classification: **{g['classification']}**",
            f"- Risk: **{g['risk']}**",
            f"- Effective provider from supplied order evidence: `{g['effective_provider'] or 'UNKNOWN'}`",
            "- Providers:",
        ]
        ranked_providers = sorted(
            g["providers"],
            key=lambda e: (rank_provider(e["arc"], order) is None,
                           rank_provider(e["arc"], order) if rank_provider(e["arc"], order) is not None else 10**12,
                           e["arc"])
        )
        for e in ranked_providers:
            r = rank_provider(e["arc"], order)
            lines.append(
                f"  - `{e['arc']}`"
                f" | order={r if r is not None else '?'}"
                f" | expanded={e['expanded_sha256'] or 'UNRESOLVED'}"
                f" | stored={e['stored_sha256']}"
                f" | flags={e['flags']}"
            )
        lines.append("")

    (outdir / "PRIORITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nOutputs: {outdir}")

if __name__ == "__main__":
    main()