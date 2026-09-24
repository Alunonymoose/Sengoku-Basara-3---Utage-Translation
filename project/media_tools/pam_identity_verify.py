#!/usr/bin/env python3
"""
BASARA Foundry PAM identity-remux verifier.

Read-only. Compares an original PAM/PAMF against a remux candidate and,
when supplied, compares the two PAMFtool demux directories byte-for-byte
at the elementary-stream/container-sidecar level.

A whole-file PAM hash mismatch is EXPECTED and is never by itself failure:
PAMFtool rebuilds PS scheduling/header/EP metadata.

Release/runtime PASS is intentionally impossible here. This tool can emit
STRUCTURAL_PASS only; RPCS3 cold-boot playback + A/V sync remains mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "BASARA_FOUNDRY_PAM_IDENTITY_VERIFY_V1"
STREAM_TYPES = {
    0x1B: "AVC",
    0x02: "MPEG2_VIDEO",
    0xDC: "ATRAC3PLUS",
    0x81: "AC3",
    0x80: "LPCM",
    0xDD: "USER_DATA",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def be16(b: bytes, off: int) -> int:
    return struct.unpack_from(">H", b, off)[0]


def be32(b: bytes, off: int) -> int:
    return struct.unpack_from(">I", b, off)[0]


def parse_scr_pack6(six: bytes) -> dict[str, int]:
    if len(six) != 6:
        raise ValueError("SCR payload must be six bytes")
    bits = "".join(f"{x:08b}" for x in six)
    if bits[:2] != "01" or bits[5] != "1" or bits[21] != "1" or bits[37] != "1" or bits[47] != "1":
        raise ValueError("not an MPEG-2 pack SCR field")
    hi = int(bits[2:5], 2)
    mid = int(bits[6:21], 2)
    lo = int(bits[22:37], 2)
    ext = int(bits[38:47], 2)
    return {"scr_base_90khz": (hi << 30) | (mid << 15) | lo, "scr_extension": ext}


def find_pack_offset(raw: bytes) -> int:
    limit = min(len(raw) - 4, 0x10000)
    for i in range(max(0, limit + 1)):
        if raw[i:i + 4] == b"\x00\x00\x01\xBA":
            return i
    raise ValueError("could not find MPEG-PS pack start within first 64 KiB")


def pstd_decode(raw: int) -> dict[str, int]:
    scale = (raw >> 13) & 1
    size = raw & 0x1FFF
    unit = 1024 if scale else 128
    return {"raw": raw, "scale": scale, "size_units": size, "bytes": size * unit}


def parse_pam(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    with path.open("rb") as f:
        prefix = f.read(min(size, 0x10000))
    if len(prefix) < 0x800 or prefix[:4] != b"PAMF":
        raise ValueError(f"{path} is not a PAMF file")

    version = prefix[4:8].decode("ascii", "replace")
    num_streams = be16(prefix, 0x86)
    if num_streams <= 0 or num_streams > 32 or 0x88 + num_streams * 0x30 > len(prefix):
        raise ValueError(f"invalid PAMF stream table count {num_streams}")

    pack_off = find_pack_offset(prefix)
    if pack_off + 10 > len(prefix):
        raise ValueError("truncated first pack")
    scr = parse_scr_pack6(prefix[pack_off + 4:pack_off + 10])

    streams = []
    for i in range(num_streams):
        off = 0x88 + i * 0x30
        typ = prefix[off]
        ci = prefix[off + 16:off + 48]
        rec: dict[str, Any] = {
            "index": i,
            "type_code": typ,
            "type": STREAM_TYPES.get(typ, f"UNKNOWN_0x{typ:02X}"),
            "channel": prefix[off + 1],
            "pes_stream_id": prefix[off + 4],
            "sub_stream_id": prefix[off + 5],
            "pstd": pstd_decode(be16(prefix, off + 6)),
            "ep_offset": be32(prefix, off + 8),
            "ep_num": be32(prefix, off + 12),
            "codec_info_hex": ci.hex(),
        }
        if typ == 0x02:
            rec.update({
                "profile_level": ci[0],
                "progressive_sequence": (ci[2] >> 7) & 1,
                "video_signal_info_flag": (ci[2] >> 6) & 1,
                "frame_rate_code": ci[2] & 0x0F,
                "aspect_ratio_idc": ci[3],
                "width": int.from_bytes(ci[12:14], "big"),
                "height": int.from_bytes(ci[14:16], "big"),
                "video_format": (ci[20] >> 5) & 7,
                "full_range": (ci[20] >> 4) & 1,
                "colour_primaries": ci[21],
                "transfer_characteristics": ci[22],
                "matrix_coefficients": ci[23],
            })
        elif typ == 0x1B:
            rec.update({
                "profile_idc": ci[0],
                "level_idc": ci[1],
                "frame_rate_code": ci[2] & 0x0F,
                "aspect_ratio_idc": ci[3],
                "width_mbs": ci[9],
                "height_mbs": ci[11],
            })
        elif typ in {0xDC, 0x81, 0x80}:
            rec.update({
                "channels": ci[2],
                "sample_rate_code": ci[3],
                "bits_per_sample_code": ci[4],
            })
        streams.append(rec)

    start_pts = (be16(prefix, 0x56) << 32) | be32(prefix, 0x58)
    end_pts = (be16(prefix, 0x5C) << 32) | be32(prefix, 0x5E)
    gp_start = (be16(prefix, 0x74) << 32) | be32(prefix, 0x76)
    gp_end = (be16(prefix, 0x7A) << 32) | be32(prefix, 0x7C)

    return {
        "path": str(path),
        "size": size,
        "sha256": sha256_file(path),
        "magic_version": prefix[:8].decode("ascii", "replace"),
        "header_sha256": hashlib.sha256(prefix[:pack_off]).hexdigest(),
        "header_sectors": be32(prefix, 0x08),
        "data_sectors": be32(prefix, 0x0C),
        "stream_offset": pack_off,
        "stream_size": size - pack_off,
        "psmf_marks_offset": be32(prefix, 0x10),
        "psmf_marks_size": be32(prefix, 0x14),
        "unknown_offset": be32(prefix, 0x18),
        "unknown_size": be32(prefix, 0x1C),
        "sequence_info_size": be32(prefix, 0x50),
        "start_pts90": start_pts,
        "end_pts90": end_pts,
        "duration_ticks90": end_pts - start_pts,
        "duration_seconds_header": (end_pts - start_pts) / 90000.0,
        "mux_rate_bound": be32(prefix, 0x62),
        "std_delay_bound": be32(prefix, 0x66),
        "total_stream_num": be32(prefix, 0x6A),
        "grouping_period_num": prefix[0x6F],
        "grouping_period_size": be32(prefix, 0x70),
        "gp_start_pts90": gp_start,
        "gp_end_pts90": gp_end,
        "group_num": prefix[0x81],
        "group_size": be32(prefix, 0x82),
        "num_streams": num_streams,
        "initial_scr": scr,
        "streams": streams,
    }


def ffprobe(path: Path) -> dict[str, Any] | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    proc = subprocess.run([
        exe, "-v", "error",
        "-show_entries",
        "format=format_name,start_time,duration,size,bit_rate:"
        "stream=index,codec_name,profile,level,width,height,r_frame_rate,avg_frame_rate,start_time,duration,channels,sample_rate",
        "-of", "json", str(path)
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": proc.stderr[-4000:], "returncode": proc.returncode}
    return json.loads(proc.stdout)


def demux_inventory(folder: Path) -> dict[str, Any]:
    if not folder.is_dir():
        raise ValueError(f"demux folder not found: {folder}")
    rows = []
    for p in sorted(x for x in folder.iterdir() if x.is_file()):
        rows.append({
            "name": p.name,
            "size": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return {"folder": str(folder), "files": rows}


def match_demux(original: dict[str, Any], remuxed: dict[str, Any]) -> dict[str, Any]:
    def key(name: str) -> str:
        # Ignore the container basename; PAMFtool suffix after first ".sNN_" is
        # the stream identity that survives an original/remux filename change.
        pos = name.find(".s")
        return name[pos + 1:].lower() if pos >= 0 else name.lower()

    a = {key(x["name"]): x for x in original["files"]}
    b = {key(x["name"]): x for x in remuxed["files"]}
    keys = sorted(set(a) | set(b))
    rows = []
    for k in keys:
        ar, br = a.get(k), b.get(k)
        rows.append({
            "stream_key": k,
            "original": ar,
            "remuxed": br,
            "present_both": ar is not None and br is not None,
            "size_equal": ar is not None and br is not None and ar["size"] == br["size"],
            "sha256_equal": ar is not None and br is not None and ar["sha256"] == br["sha256"],
        })
    return {
        "all_present": all(r["present_both"] for r in rows),
        "all_sha256_equal": bool(rows) and all(r["sha256_equal"] for r in rows),
        "rows": rows,
    }


def compare_headers(a: dict[str, Any], b: dict[str, Any], duration_tolerance_ticks: int) -> list[dict[str, Any]]:
    checks = []

    def add(name: str, av: Any, bv: Any, required: bool = True, tolerance: int | float | None = None):
        if tolerance is None:
            ok = av == bv
        else:
            try:
                ok = abs(av - bv) <= tolerance
            except Exception:
                ok = False
        checks.append({
            "field": name,
            "original": av,
            "remuxed": bv,
            "required_for_structural_pass": required,
            "tolerance": tolerance,
            "pass": ok,
        })

    add("magic_version", a["magic_version"], b["magic_version"])
    add("num_streams", a["num_streams"], b["num_streams"])
    add("total_stream_num", a["total_stream_num"], b["total_stream_num"])
    add("header_sectors", a["header_sectors"], b["header_sectors"])
    add("stream_offset", a["stream_offset"], b["stream_offset"])
    add("start_pts90", a["start_pts90"], b["start_pts90"])
    add("gp_start_pts90", a["gp_start_pts90"], b["gp_start_pts90"])
    add("end_pts90", a["end_pts90"], b["end_pts90"], True, duration_tolerance_ticks)
    add("gp_end_pts90", a["gp_end_pts90"], b["gp_end_pts90"], True, duration_tolerance_ticks)
    add("duration_ticks90", a["duration_ticks90"], b["duration_ticks90"], True, duration_tolerance_ticks)
    add("mux_rate_bound", a["mux_rate_bound"], b["mux_rate_bound"])
    add("std_delay_bound", a["std_delay_bound"], b["std_delay_bound"])
    add("initial_scr_base", a["initial_scr"]["scr_base_90khz"], b["initial_scr"]["scr_base_90khz"])
    add("initial_scr_extension", a["initial_scr"]["scr_extension"], b["initial_scr"]["scr_extension"], False)
    add("grouping_period_num", a["grouping_period_num"], b["grouping_period_num"])
    add("group_num", a["group_num"], b["group_num"])

    if len(a["streams"]) == len(b["streams"]):
        for i, (sa, sb) in enumerate(zip(a["streams"], b["streams"])):
            prefix = f"stream[{i}]"
            for field in ("type_code", "channel", "pes_stream_id", "sub_stream_id"):
                add(f"{prefix}.{field}", sa.get(field), sb.get(field))
            # P-STD is decoder-relevant and is a hard identity-remux requirement.
            add(f"{prefix}.pstd.raw", sa["pstd"]["raw"], sb["pstd"]["raw"])
            add(f"{prefix}.pstd.bytes", sa["pstd"]["bytes"], sb["pstd"]["bytes"])
            # Exact codec-info parity is desirable for an untouched identity remux.
            add(f"{prefix}.codec_info_hex", sa["codec_info_hex"], sb["codec_info_hex"])

    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify an Utage PAM identity remux")
    ap.add_argument("--original", required=True, type=Path)
    ap.add_argument("--remux", required=True, type=Path)
    ap.add_argument("--original-demux", type=Path)
    ap.add_argument("--remux-demux", type=Path)
    ap.add_argument("--duration-tolerance-ticks", type=int, default=3003,
                    help="Default one 29.97fps frame at 90 kHz.")
    ap.add_argument("--out", required=True, type=Path)
    ns = ap.parse_args()

    original = parse_pam(ns.original.resolve())
    remuxed = parse_pam(ns.remux.resolve())
    checks = compare_headers(original, remuxed, ns.duration_tolerance_ticks)

    demux_compare = None
    if bool(ns.original_demux) != bool(ns.remux_demux):
        raise SystemExit("--original-demux and --remux-demux must be supplied together")
    if ns.original_demux and ns.remux_demux:
        od = demux_inventory(ns.original_demux.resolve())
        rd = demux_inventory(ns.remux_demux.resolve())
        demux_compare = match_demux(od, rd)

    hard_header_pass = all(c["pass"] for c in checks if c["required_for_structural_pass"])
    demux_pass = demux_compare is not None and demux_compare["all_sha256_equal"]
    structural_pass = hard_header_pass and demux_pass

    result = {
        "schema": SCHEMA,
        "status": "STRUCTURAL_PASS" if structural_pass else "FAIL",
        "runtime_status": "NOT_TESTED",
        "runtime_pass_required": True,
        "whole_pam_hash_equal": original["sha256"] == remuxed["sha256"],
        "whole_pam_hash_note": (
            "Whole-PAM equality is not required: PAMFtool regenerates PS/header scheduling metadata."
        ),
        "original": original,
        "remuxed": remuxed,
        "header_checks": checks,
        "demux_compare": demux_compare,
        "ffprobe": {
            "original": ffprobe(ns.original.resolve()),
            "remuxed": ffprobe(ns.remux.resolve()),
        },
        "structural_pass_requirements": [
            "same stream set and exact re-demuxed elementary/AT3 hashes",
            "PAMF magic/version, header start PTS and stream-table identity",
            "decoder-relevant P-STD parity",
            "mux_rate/std_delay/initial SCR parity",
            "header duration within configured tolerance",
        ],
        "final_pass_requirements": [
            "STRUCTURAL_PASS",
            "replace exact target path on a recoverable copy of current E:",
            "RPCS3 cold boot",
            "scene plays start-to-finish",
            "audio/video synchronization acceptable",
            "scene exits/returns to game normally",
            "runtime evidence bound to remux SHA-256",
        ],
    }

    out = ns.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "original_sha256": original["sha256"],
        "remux_sha256": remuxed["sha256"],
        "whole_pam_hash_equal": result["whole_pam_hash_equal"],
        "hard_header_pass": hard_header_pass,
        "demux_stream_hash_pass": demux_pass,
        "runtime_status": "NOT_TESTED",
        "report": str(out),
    }, indent=2))
    return 0 if structural_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
