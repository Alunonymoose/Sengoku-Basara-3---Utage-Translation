#!/usr/bin/env python3
"""Utage Harness: BASARA-specific offline verifier / partial 2D runtime.

This is deliberately not a PS3 emulator. It reuses current BASARA Foundry
parsers/codecs, renders known 2D composition contracts, and correlates RPCS3
RRC v6 active memory with exact live ARC members.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, struct, sys
from collections import Counter
from pathlib import Path
from typing import Iterable
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ALRUMMI = PROJECT / "Alrummi3"
XET_TOOLS = PROJECT / "texture_tools" / "xet_ps3_2026-09-25"
for p in (str(ALRUMMI), str(XET_TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)
import alrummi3_core as core
import layout as lsp
import xet_ps3

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def norm_name(name: str) -> str:
    return name.replace("/", "\\").lower()

def find_entry(arc, selector: str):
    try:
        idx = int(selector)
        return arc.entries[idx]
    except (ValueError, IndexError):
        pass
    key = norm_name(selector)
    exact = [e for e in arc.entries if norm_name(e.name) == key]
    if len(exact) == 1:
        return exact[0]
    tail = key.split("\\")[-1]
    hits = [e for e in arc.entries if norm_name(e.name).split("\\")[-1] == tail]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise KeyError(f"member not found: {selector}")
    raise KeyError(f"ambiguous member {selector}: {[e.name for e in hits[:8]]}")

def decode_member(arc, entry):
    raw = core.unpack_entry(entry)
    if raw[:4] == b"\0XET":
        arr = xet_ps3.decode_display(raw)
        return Image.fromarray(arr, "RGBA"), raw
    image, _meta = core.decode_resource(raw, entry.name)
    return image, raw

def texture_meta(raw: bytes) -> dict:
    i = xet_ps3.info(raw)
    return {
        "width": i["width"], "height": i["height"], "format": f"0x{i['format']:02X}",
        "mips": i["mips"], "mip_offsets": i["mip_offsets"],
        "display_codec": "YCbCr shader emulation" if i["format"] == 0x2A else "plain RGBA/BC",
    }

def arc_report(path: Path) -> dict:
    arc = core.parse_arc(path)
    counts = Counter(core.type_label(e.type_hash, e.name) for e in arc.entries)
    textures, texture_errors, layouts = [], [], []
    for e in arc.entries:
        try:
            raw = core.unpack_entry(e)
        except Exception as exc:
            texture_errors.append({"member": e.name, "error": f"unpack: {exc}"})
            continue
        if raw[:4] == b"\0XET":
            try:
                textures.append({"index": e.index, "member": e.name, **texture_meta(raw)})
            except Exception as exc:
                texture_errors.append({"member": e.name, "error": str(exc)})
        if lsp.is_layout(raw):
            try:
                x = lsp.parse_layout(raw, e.name)
                layouts.append({
                    "member": e.name, "version": x.version, "declared_nodes": x.node_count,
                    "recovered_nodes": len(x.nodes), "textures": x.textures,
                    "complete_name_sweep": x.complete,
                })
            except Exception as exc:
                layouts.append({"member": e.name, "error": str(exc)})
    return {
        "archive": str(path), "sha256": arc.data_sha256 or sha_file(path),
        "version": arc.version, "endian": arc.endian, "platform": arc.platform,
        "entry_count": len(arc.entries), "alignment": core.detect_alignment(arc),
        "type_counts": dict(counts), "textures": textures,
        "texture_errors": texture_errors, "layouts": layouts,
    }

def cmd_arc_report(args):
    report = arc_report(Path(args.arc))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")

def cmd_preview(args):
    arc = core.parse_arc(Path(args.arc))
    e = find_entry(arc, args.member)
    image, raw = decode_member(arc, e)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    meta = {"archive_sha256": arc.data_sha256, "index": e.index, "member": e.name,
            "raw_sha256": sha256(raw), "size": list(image.size)}
    if raw[:4] == b"\0XET":
        meta.update(texture_meta(raw))
    print(json.dumps(meta, indent=2))

def compare_arcs(a: Path, b: Path) -> dict:
    aa, bb = core.parse_arc(a), core.parse_arc(b)
    ma = {(norm_name(e.name), e.type_hash): e for e in aa.entries}
    mb = {(norm_name(e.name), e.type_hash): e for e in bb.entries}
    added, removed, changed, same = [], [], [], 0
    for k in sorted(ma.keys() | mb.keys()):
        if k not in ma:
            added.append(mb[k].name); continue
        if k not in mb:
            removed.append(ma[k].name); continue
        ra, rb = core.unpack_entry(ma[k]), core.unpack_entry(mb[k])
        if ra == rb:
            same += 1
        else:
            changed.append({"member": ma[k].name, "a_sha256": sha256(ra),
                            "b_sha256": sha256(rb), "a_size": len(ra), "b_size": len(rb)})
    return {"a": str(a), "b": str(b), "a_sha256": aa.data_sha256,
            "b_sha256": bb.data_sha256, "same_members": same,
            "changed": changed, "added": added, "removed": removed}

def cmd_compare(args):
    print(json.dumps(compare_arcs(Path(args.a), Path(args.b)), indent=2))

def load_scene_image(layer: dict, scene_dir: Path):
    arc_path = Path(layer["archive"])
    if not arc_path.is_absolute():
        arc_path = (scene_dir / arc_path).resolve()
    arc = core.parse_arc(arc_path)
    entry = find_entry(arc, str(layer["member"]))
    image, raw = decode_member(arc, entry)
    src = layer.get("source")
    if src:
        x, y, w, h = src
        image = image.crop((x, y, x + w, y + h))
    return image, arc, entry, raw

def cmd_render_scene(args):
    scene_path = Path(args.scene)
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    w, h = scene.get("size", [1280, 720])
    bg = tuple(scene.get("background", [0, 0, 0, 0]))
    canvas = Image.new("RGBA", (w, h), bg)
    scale = float(scene.get("logical_scale", 2.0))
    evidence = []
    for n, layer in enumerate(scene.get("layers", [])):
        if layer.get("visible", True) is False:
            continue
        image, arc, entry, raw = load_scene_image(layer, scene_path.parent)
        dest = layer.get("dest", [0, 0, image.width, image.height])
        x, y, dw, dh = dest
        if layer.get("logical", False):
            x, y, dw, dh = [round(v * scale) for v in (x, y, dw, dh)]
        if image.size != (dw, dh):
            resample = Image.Resampling.NEAREST if layer.get("sampling") == "nearest" else Image.Resampling.BICUBIC
            image = image.resize((dw, dh), resample)
        opacity = float(layer.get("opacity", 1.0))
        if opacity != 1.0:
            a = image.getchannel("A").point(lambda v: max(0, min(255, round(v * opacity))))
            image.putalpha(a)
        canvas.alpha_composite(image, (int(x), int(y)))
        evidence.append({"layer": n, "arc_sha256": arc.data_sha256, "member": entry.name,
                         "raw_sha256": sha256(raw), "dest": [x, y, dw, dh]})
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); canvas.save(out)
    print(json.dumps({"out": str(out), "size": [w, h], "layers": evidence}, indent=2))

class R:
    def __init__(self, data: bytes): self.d, self.p = data, 0
    def raw(self, n):
        if self.p + n > len(self.d): raise ValueError("truncated RRC")
        x = self.d[self.p:self.p+n]; self.p += n; return x
    def u32(self): return struct.unpack("<I", self.raw(4))[0]
    def u64(self): return struct.unpack("<Q", self.raw(8))[0]
    def vle(self):
        out = shift = 0
        while True:
            b = self.raw(1)[0]; out |= (b & 0x7f) << shift
            if not b & 0x80: return out
            shift += 7
            if shift >= 35: raise ValueError("bad RRC VLE")

RRC_VP_WORDS = 544 * 4
RRC_REGISTER_WORDS = 0x10000 // 4
RRC_STATE_BYTES = (RRC_VP_WORDS + RRC_REGISTER_WORDS) * 4

def _f32le_word(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]

def _packed_origin_size(value: int) -> dict:
    return {"origin": value & 0xFFFF, "size": (value >> 16) & 0xFFFF,
            "raw": f"0x{value:08x}"}

def decode_rrc_register_state(raw: bytes, offset: int) -> dict:
    """Decode the initial rsx_state serialized at the end of RPCS3 RRC v6.

    Current RPCS3 frame capture serializes 544*4 transform-program u32s
    followed directly by the 0x10000-byte RSX method-register array.
    """
    tail = raw[offset:]
    if len(tail) != RRC_STATE_BYTES:
        raise ValueError(
            f"unexpected RRC rsx_state size {len(tail)}; expected {RRC_STATE_BYTES}")
    vp_bytes = RRC_VP_WORDS * 4
    registers = struct.unpack(
        f"<{RRC_REGISTER_WORDS}I", tail[vp_bytes:vp_bytes + 0x10000])

    def reg(byte_address: int) -> int:
        return registers[byte_address >> 2]

    def f4(byte_address: int) -> list[float]:
        return [_f32le_word(reg(byte_address + i * 4)) for i in range(4)]

    surface_x = _packed_origin_size(reg(0x0200))
    surface_y = _packed_origin_size(reg(0x0204))
    scissor_x = _packed_origin_size(reg(0x08C0))
    scissor_y = _packed_origin_size(reg(0x08C4))
    viewport_x = _packed_origin_size(reg(0x0A00))
    viewport_y = _packed_origin_size(reg(0x0A04))
    return {
        "serialized_bytes": len(tail),
        "transform_program_bytes": vp_bytes,
        "register_bytes": 0x10000,
        "tail_sha256": sha256(tail),
        "surface_clip": {
            "x": surface_x["origin"], "y": surface_y["origin"],
            "width": surface_x["size"], "height": surface_y["size"],
            "raw_horizontal": surface_x["raw"], "raw_vertical": surface_y["raw"],
        },
        "scissor": {
            "x": scissor_x["origin"], "y": scissor_y["origin"],
            "width": scissor_x["size"], "height": scissor_y["size"],
            "raw_horizontal": scissor_x["raw"], "raw_vertical": scissor_y["raw"],
        },
        "viewport_rect": {
            "x": viewport_x["origin"], "y": viewport_y["origin"],
            "width": viewport_x["size"], "height": viewport_y["size"],
            "raw_horizontal": viewport_x["raw"], "raw_vertical": viewport_y["raw"],
        },
        "viewport_offset": f4(0x0A20),
        "viewport_scale": f4(0x0A30),
    }

def parse_rrc(path: Path):
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b" or path.suffix.lower() == ".gz":
        raw = gzip.decompress(raw)
    r = R(raw)
    if r.u32() != 0x00435252: raise ValueError("not RRC")
    version, le = r.u32(), r.u32()
    if version != 6 or le != 1: raise ValueError(f"unsupported RRC v{version}, LE={le}")
    for _ in range(r.vle()): r.raw(432); r.u64()
    blocks = {}
    for _ in range(r.vle()):
        off, loc, state, bh = r.u32(), r.u32(), r.u64(), r.u64()
        blocks[bh] = (off, loc, state)
    payloads = {}
    for _ in range(r.vle()):
        blob = r.raw(r.vle()); payloads[r.u64()] = blob
    display_states = {}
    for _ in range(r.vle()):
        blob = r.raw(132)
        state_hash = r.u64()
        words = struct.unpack("<33I", blob)
        count = min(words[32], 8)
        display_states[state_hash] = {
            "count": count,
            "buffers": [
                {"width": words[i * 4], "height": words[i * 4 + 1],
                 "pitch": words[i * 4 + 2], "offset": words[i * 4 + 3]}
                for i in range(count)
            ],
        }

    active = set(); active_display = set(); command_rows = []
    commands = r.vle()
    for command_index in range(commands):
        first, value = r.u32(), r.u32()
        memory_refs = [r.u64() for _ in range(r.vle())]
        active.update(memory_refs)
        tile_state = r.u64()
        display_state = r.u64()
        if display_state:
            active_display.add(display_state)
        command_rows.append({
            "index": command_index, "first": first, "value": value,
            "memory_refs": memory_refs, "tile_state": tile_state,
            "display_state": display_state,
        })
    states = {blocks[h][2] for h in active if h in blocks}
    rsx_state = decode_rrc_register_state(raw, r.p)
    register_blob = raw[
        r.p + RRC_VP_WORDS * 4:
        r.p + RRC_VP_WORDS * 4 + 0x10000]
    initial_registers = struct.unpack(f"<{RRC_REGISTER_WORDS}I", register_blob)
    return {"version": version, "commands": commands, "command_rows": command_rows,
            "initial_registers": initial_registers,
            "blocks": blocks, "payloads": payloads,
            "display_states": display_states, "active_display_states": active_display,
            "active_blocks": active, "active_states": states,
            "decompressed_size": len(raw), "reg_state_offset": r.p,
            "rsx_state": rsx_state}

def cmd_rrc_info(args):
    p = parse_rrc(Path(args.capture))
    active_bytes = sum(len(p["payloads"][s]) for s in p["active_states"])
    out = {"capture": args.capture, "version": p["version"], "replay_commands": p["commands"],
           "memory_blocks": len(p["blocks"]), "payloads_total": len(p["payloads"]),
           "active_blocks": len(p["active_blocks"]), "active_unique_payloads": len(p["active_states"]),
           "active_payload_bytes": active_bytes, "reg_state_offset": p["reg_state_offset"],
           "rsx_state_bytes": p["rsx_state"]["serialized_bytes"],
           "surface_clip": p["rsx_state"]["surface_clip"],
           "viewport_rect": p["rsx_state"]["viewport_rect"],
           "viewport_offset": p["rsx_state"]["viewport_offset"],
           "viewport_scale": p["rsx_state"]["viewport_scale"]}
    print(json.dumps(out, indent=2))

RSX_METHOD_NAMES = {
    0x0200: "surface_clip_horizontal",
    0x0204: "surface_clip_vertical",
    0x0304: "alpha_test_enable",
    0x0308: "alpha_func",
    0x030C: "alpha_ref",
    0x0310: "blend_enable",
    0x0314: "blend_src_factor",
    0x0318: "blend_dst_factor",
    0x031C: "blend_color",
    0x0320: "blend_equation",
    0x08C0: "scissor_horizontal",
    0x08C4: "scissor_vertical",
    0x0A00: "viewport_horizontal",
    0x0A04: "viewport_vertical",
    0x0A20: "viewport_offset_x",
    0x0A24: "viewport_offset_y",
    0x0A28: "viewport_offset_z",
    0x0A2C: "viewport_offset_w",
    0x0A30: "viewport_scale_x",
    0x0A34: "viewport_scale_y",
    0x0A38: "viewport_scale_z",
    0x0A3C: "viewport_scale_w",
    0x1808: "begin_end",
}

BLEND_FACTOR_NAMES = {
    0x0000: "zero", 0x0001: "one",
    0x0300: "src_color", 0x0301: "one_minus_src_color",
    0x0302: "src_alpha", 0x0303: "one_minus_src_alpha",
    0x0304: "dst_alpha", 0x0305: "one_minus_dst_alpha",
    0x0306: "dst_color", 0x0307: "one_minus_dst_color",
    0x0308: "src_alpha_saturate",
    0x8001: "constant_color", 0x8002: "one_minus_constant_color",
    0x8003: "constant_alpha", 0x8004: "one_minus_constant_alpha",
}
BLEND_EQUATION_NAMES = {
    0x8006: "add", 0x8007: "min", 0x8008: "max",
    0x800A: "subtract", 0x800B: "reverse_subtract",
}

def _method_address(first):
    return first & 0x3FFFF

def _pipeline_snapshot(registers):
    def reg(addr): return registers[addr >> 2]
    def packed_pair(value, names):
        lo, hi = value & 0xFFFF, (value >> 16) & 0xFFFF
        return {
            "rgb_raw": f"0x{lo:04x}", "alpha_raw": f"0x{hi:04x}",
            "rgb": names.get(lo, "unknown"), "alpha": names.get(hi, "unknown"),
        }
    sx, sy = _packed_origin_size(reg(0x0200)), _packed_origin_size(reg(0x0204))
    vx, vy = _packed_origin_size(reg(0x0A00)), _packed_origin_size(reg(0x0A04))
    return {
        "surface_clip": [sx["origin"], sy["origin"], sx["size"], sy["size"]],
        "viewport_rect": [vx["origin"], vy["origin"], vx["size"], vy["size"]],
        "viewport_offset": [_f32le_word(reg(0x0A20 + i * 4)) for i in range(4)],
        "viewport_scale": [_f32le_word(reg(0x0A30 + i * 4)) for i in range(4)],
        "blend_enable": bool(reg(0x0310)),
        "blend_src": packed_pair(reg(0x0314), BLEND_FACTOR_NAMES),
        "blend_dst": packed_pair(reg(0x0318), BLEND_FACTOR_NAMES),
        "blend_equation": packed_pair(reg(0x0320), BLEND_EQUATION_NAMES),
        "alpha_test_enable": bool(reg(0x0304)),
        "alpha_func_raw": f"0x{reg(0x0308):08x}",
        "alpha_ref_raw": f"0x{reg(0x030C):08x}",
    }

def _rrc_draw_snapshots(parsed):
    registers = list(parsed["initial_registers"])
    draws = []
    interesting_writes = []
    for row in parsed["command_rows"]:
        method = _method_address(row["first"])
        if method < 0x10000:
            registers[method >> 2] = row["value"]
        if method in RSX_METHOD_NAMES:
            interesting_writes.append({
                "command": row["index"], "method": RSX_METHOD_NAMES[method],
                "address": f"0x{method:04x}", "value": f"0x{row['value']:08x}"})
        if method == 0x1808 and row["value"] != 0:
            display = parsed["display_states"].get(row["display_state"])
            draws.append({
                "command": row["index"], "primitive_raw": row["value"],
                "display_state": (
                    f"0x{row['display_state']:016x}" if row["display_state"] else None),
                "display_buffers": display,
                "memory_ref_count": len(row["memory_refs"]),
                "pipeline": _pipeline_snapshot(registers),
            })
    return draws, interesting_writes

def cmd_rrc_state(args):
    p = parse_rrc(Path(args.capture))
    draws, writes = _rrc_draw_snapshots(p)
    active_displays = [
        {"hash": f"0x{h:016x}", **p["display_states"][h]}
        for h in sorted(p["active_display_states"])
        if h in p["display_states"]
    ]
    print(json.dumps({
        "capture": args.capture, **p["rsx_state"],
        "initial_pipeline": _pipeline_snapshot(p["initial_registers"]),
        "active_display_states": active_displays,
        "draw_call_count": len(draws),
        "interesting_method_write_count": len(writes),
    }, indent=2))

def cmd_rrc_draws(args):
    p = parse_rrc(Path(args.capture))
    draws, writes = _rrc_draw_snapshots(p)
    if args.unique:
        seen = set(); unique = []
        for draw in draws:
            key = json.dumps(draw["pipeline"], sort_keys=True)
            if key not in seen:
                seen.add(key); unique.append(draw)
        draws = unique
    if args.limit is not None:
        draws = draws[:args.limit]
    print(json.dumps({
        "capture": args.capture, "draw_count_total": len(_rrc_draw_snapshots(p)[0]),
        "returned": len(draws), "draws": draws,
        "interesting_writes": writes if args.writes else None,
    }, indent=2))

def variants_for_member(raw: bytes) -> Iterable[tuple[str, bytes]]:
    yield "whole", raw
    if len(raw) > 20: yield "skip_20", raw[20:]
    if raw[:4] == b"\0XET":
        try:
            i = xet_ps3.info(raw); off = i["mip_offsets"][0]
            yield "xet_mip0_to_eof", raw[off:]
            # Exact level-0 block bytes, excluding possible later mips/trailing data.
            bs = 8 if i["format"] == 0x19 else 16
            size = ((i["width"] + 3)//4) * ((i["height"] + 3)//4) * bs
            yield "xet_mip0_level", raw[off:off+size]
        except Exception:
            pass

def cmd_rrc_match_arc(args):
    p = parse_rrc(Path(args.capture))
    sigs = {}
    for s in p["active_states"]:
        blob = p["payloads"][s]
        sigs.setdefault((len(blob), sha256(blob)), []).append(s)
    arc = core.parse_arc(Path(args.arc))
    matches = []
    for e in arc.entries:
        try: raw = core.unpack_entry(e)
        except Exception: continue
        for mode, blob in variants_for_member(raw):
            states = sigs.get((len(blob), sha256(blob)))
            if states:
                matches.append({"index": e.index, "member": e.name, "mode": mode,
                                "size": len(blob), "sha256": sha256(blob),
                                "data_states": [f"0x{x:016x}" for x in states]})
    print(json.dumps({"capture": args.capture, "arc": args.arc,
                      "arc_sha256": arc.data_sha256, "matches": matches}, indent=2))

def node_info(layout, node, atlas_scale=2.0):
    return {
        "index": node.index, "node_id": node.node_id, "name": node.name, "role": node.role,
        "type": node.node_type, "parent": node.parent, "texture": node.texture,
        "position": list(node.position), "rotation_deg": node.rotation,
        "scale": list(node.scale),
        "geometry": list(node.geometry), "uv_logical": list(node.uv),
        "source_rect_physical": list(node.source_rect(atlas_scale)),
        "world_transform": list(layout.world_transform(node.index)),
        "dest_bbox_logical": list(layout.logical_bbox(node.index)),
        "colors": [f"0x{c:08x}" for c in node.colors],
        "shader_type": node.shader_type, "blend_state": node.blend_state,
        "links": {"3c": node.link_3c, "40": node.link_40, "44": node.link_44},
        "mask_node": (layout.mask_for(node.index).index if layout.mask_for(node.index) else None),
        "mask_node_id": (layout.mask_for(node.index).node_id if layout.mask_for(node.index) else None),
    }

def cmd_layouts(args):
    arc = core.parse_arc(Path(args.arc))
    out = []
    for x in lsp.layouts_in_archive(arc):
        out.append({"member": x.name, "version": x.version, "declared_nodes": x.node_count,
                    "recovered_nodes": len(x.nodes), "textures": x.textures,
                    "animation_count": len(x.animations),
                    "animation_parse_error": x.animation_parse_error,
                    "animation_roots": [
                        {"index": a.index, "name": a.name, "type": a.record_type,
                         "target_node": a.target_node, "duration": a.duration}
                        for a in x.animation_roots],
                    "name_table_offset": x.name_table_offset, "name_table_end": x.name_table_end,
                    "nodes": [node_info(x, n) for n in x.nodes]})
    print(json.dumps({"archive": args.arc, "sha256": arc.data_sha256, "layouts": out},
                     indent=2, ensure_ascii=False))

def get_layout(arc, selector):
    entries = []
    for e in arc.entries:
        try:
            raw = core.unpack_entry(e)
        except Exception:
            continue
        if lsp.is_layout(raw):
            entries.append((e, raw))
    if not entries:
        raise KeyError("archive contains no PSL layouts")
    if selector:
        key = norm_name(selector)
        hits = [(e, raw) for e, raw in entries
                if norm_name(e.name) == key or norm_name(e.name).endswith("\\" + key)]
        if len(hits) != 1:
            raise KeyError(f"layout selector {selector!r} matched {len(hits)} entries")
        e, raw = hits[0]
    elif len(entries) == 1:
        e, raw = entries[0]
    else:
        raise KeyError("archive has multiple layouts; pass --layout")
    return e, lsp.parse_layout(raw, e.name)

def cmd_layout_nodes(args):
    arc = core.parse_arc(Path(args.arc))
    entry, layout = get_layout(arc, args.layout)
    nodes = layout.nodes
    if args.match:
        needle = args.match.casefold()
        nodes = [n for n in nodes if needle in n.name.casefold()
                 or needle in n.texture.casefold()]
    print(json.dumps({
        "archive": args.arc, "archive_sha256": arc.data_sha256,
        "layout": entry.name, "version": layout.version,
        "node_count": layout.node_count,
        "nodes": [node_info(layout, n, args.atlas_scale) for n in nodes],
    }, indent=2, ensure_ascii=False))

def cmd_psl_sweep(args):
    root = Path(args.root)
    arcs = [root] if root.is_file() else list(root.rglob("*.arc"))
    arc_ok = arc_fail = layout_count = layout_fail = node_count = animation_count = 0
    unresolved_target_count = duplicate_node_id_count = mask_link_count = resolved_mask_count = 0
    failures = []
    reference_warnings = []
    for path in arcs:
        try:
            arc = core.parse_arc(path)
            arc_ok += 1
        except Exception as exc:
            arc_fail += 1
            failures.append({"arc": str(path), "stage": "arc", "error": str(exc)})
            continue
        for entry in arc.entries:
            if entry.type_hash != 0x60DD1B16 and not entry.name.lower().endswith(".lsp"):
                continue
            try:
                raw = core.unpack_entry(entry)
                if not lsp.is_layout(raw):
                    continue
                layout = lsp.parse_layout(raw, entry.name)
                layout_count += 1
                node_count += len(layout.nodes)
                animation_count += len(layout.animations)

                id_groups = {}
                for node in layout.nodes:
                    id_groups.setdefault(node.node_id, []).append(node.index)
                    if node.link_40 >= 0:
                        mask_link_count += 1
                        if layout.mask_for(node.index) is not None:
                            resolved_mask_count += 1
                duplicate_ids = {
                    node_id: indexes for node_id, indexes in id_groups.items()
                    if len(indexes) > 1
                }
                duplicate_node_id_count += len(duplicate_ids)

                unresolved_targets = [
                    {"animation": animation.index, "name": animation.name,
                     "target_id": animation.target_node}
                    for animation in layout.animations
                    if animation.target_node >= 0
                    and layout.animation_target(animation) is None
                ]
                unresolved_target_count += len(unresolved_targets)
                if duplicate_ids or unresolved_targets:
                    reference_warnings.append({
                        "arc": str(path), "member": entry.name,
                        "duplicate_node_ids": duplicate_ids,
                        "unresolved_animation_targets": unresolved_targets,
                    })

                if (not layout.complete or len(layout.animations) != layout.aux_count
                        or layout.animation_parse_error):
                    layout_fail += 1
                    failures.append({
                        "arc": str(path), "member": entry.name,
                        "nodes": [len(layout.nodes), layout.node_count],
                        "animations": [len(layout.animations), layout.aux_count],
                        "error": layout.animation_parse_error,
                    })
            except Exception as exc:
                layout_fail += 1
                failures.append({
                    "arc": str(path), "member": entry.name,
                    "stage": "layout", "error": str(exc),
                })
    report = {
        "root": str(root), "arcs": len(arcs), "arc_ok": arc_ok,
        "arc_fail": arc_fail, "layouts": layout_count,
        "layout_fail": layout_fail, "nodes": node_count,
        "animations": animation_count,
        "unresolved_animation_targets": unresolved_target_count,
        "duplicate_node_ids": duplicate_node_id_count,
        "mask_links": mask_link_count,
        "resolved_type5_masks": resolved_mask_count,
        "reference_warnings": reference_warnings,
        "failures": failures,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    if arc_fail or layout_fail:
        raise RuntimeError(
            f"PSL sweep failed: {arc_fail} ARC failure(s), {layout_fail} layout failure(s)")

def cmd_layout_animations(args):
    arc = core.parse_arc(Path(args.arc))
    entry, layout = get_layout(arc, args.layout)
    if not layout.animations:
        print(json.dumps({
            "archive": args.arc, "layout": entry.name,
            "animation_count": 0,
            "animation_parse_error": layout.animation_parse_error,
        }, indent=2))
        return
    records = layout.animations
    if args.root is not None:
        root = _resolve_animation_root(layout, args.root)
        records = layout.animation_tree(root.index)
    if args.match:
        needle = args.match.casefold()
        records = [a for a in records if needle in a.name.casefold()
                   or ((target := layout.animation_target(a)) is not None
                       and needle in target.name.casefold())]
    out = []
    for animation in records:
        target = layout.animation_target(animation)
        target_name = target.name if target is not None else ""
        channels = []
        for channel in animation.channels:
            if channel.stride_words is None:
                if channel.scalar:
                    channels.append({
                        "index": channel.index, "name": channel.name,
                        "scalar": channel.scalar})
            elif channel.keys:
                channels.append({
                    "index": channel.index, "name": channel.name,
                    "key_count": len(channel.keys),
                    "first_time": channel.keys[0].time,
                    "last_time": channel.keys[-1].time})
        out.append({
            "index": animation.index, "name": animation.name,
            "type": animation.record_type,
            "target_id": animation.target_node,
            "target_index": target.index if target is not None else None,
            "target_name": target_name,
            "duration": animation.duration,
            "parent_animation": animation.parent_animation,
            "offset": animation.offset, "size": animation.size,
            "channels": channels,
        })
    print(json.dumps({
        "archive": args.arc, "archive_sha256": arc.data_sha256,
        "layout": entry.name, "animation_count": len(layout.animations),
        "roots": [{"index": a.index, "name": a.name} for a in layout.animation_roots],
        "records": out,
    }, indent=2, ensure_ascii=False))


def _sample_animation_key(channel, frame):
    if not channel.keys:
        return None
    selected = channel.keys[0]
    for key in channel.keys:
        if key.time > frame:
            break
        selected = key
    return selected

def _key_pair(channel, frame):
    if not channel.keys:
        return None, None, 0.0
    if frame <= channel.keys[0].time:
        return channel.keys[0], channel.keys[0], 0.0
    if frame >= channel.keys[-1].time:
        return channel.keys[-1], channel.keys[-1], 0.0
    left = channel.keys[0]
    for right in channel.keys[1:]:
        if frame == right.time:
            return right, right, 0.0
        if frame < right.time:
            span = max(1, right.time - left.time)
            t = (frame - left.time) / span
            if left.interpolation == 5:
                t = t * t * (3.0 - 2.0 * t)
            elif left.interpolation not in (3, 5):
                t = 0.0
            return left, right, t
        left = right
    return left, left, 0.0

def _lerp_argb(a, b, t):
    out = 0
    for shift in (24, 16, 8, 0):
        av, bv = (a >> shift) & 0xFF, (b >> shift) & 0xFF
        out |= max(0, min(255, round(av + (bv - av) * t))) << shift
    return out

def _sample_channel(channel, frame):
    left, right, t = _key_pair(channel, frame)
    if left is None:
        return None
    if channel.name in ("position", "rotation", "scale"):
        a = left.float_values()
        if left is right or t <= 0.0:
            return a
        b = right.float_values()
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(min(len(a), len(b))))
    if channel.name in ("geometry_rect", "uv_rect"):
        def signed(v):
            return v - 0x100000000 if v & 0x80000000 else v
        a = tuple(signed(v) for v in left.values) if channel.name == "geometry_rect" else left.values
        if left is right or t <= 0.0:
            return a
        b = tuple(signed(v) for v in right.values) if channel.name == "geometry_rect" else right.values
        return tuple(round(a[i] + (b[i] - a[i]) * t)
                     for i in range(min(len(a), len(b))))
    if channel.name.startswith("color_") and left.values:
        if left is right or t <= 0.0 or not right.values:
            return (left.values[0],)
        return (_lerp_argb(left.values[0], right.values[0], t),)
    return left.values

def _resolve_animation_root(layout, selector):
    """Resolve any animation/control record; retain the legacy helper name for CLI compatibility."""
    if selector is None:
        return None
    try:
        idx = int(selector)
        matches = [a for a in layout.animations if a.index == idx]
    except ValueError:
        needle = selector.casefold()
        exact = [a for a in layout.animations if a.name.casefold() == needle]
        matches = exact if exact else [
            a for a in layout.animations if needle in a.name.casefold()]
    if len(matches) != 1:
        raise KeyError(f"animation selector {selector!r} matched {len(matches)} records")
    selected = matches[0]
    direct = [a for a in layout.animations if a.parent_animation == selected.index]
    child_groups = [a for a in direct if a.target_node < 0]
    if selected.target_node < 0 and len(child_groups) > 1:
        labels = ", ".join(f"{a.index}:{a.name}" for a in child_groups)
        raise ValueError(
            f"animation {selected.index}:{selected.name} is a container with multiple clips; "
            f"select one child clip explicitly ({labels})")
    return selected

def _animated_local_states(layout, root, frame):
    states = {
        n.index: {
            "position": list(n.position), "scale": list(n.scale),
            "geometry": list(n.geometry), "uv": list(n.uv), "colors": list(n.colors),
            "rotation": [0.0, 0.0, n.rotation, 0.0],
            "visible": True, "shake": False,
        }
        for n in layout.nodes
    }
    if root is None:
        return states, []
    warnings = []
    selected_tree = layout.animation_tree(root.index)
    if any(
        key.interpolation == 5
        for animation in selected_tree
        for channel in animation.channels
        for key in channel.keys
    ):
        warnings.append(
            "interpolation code 5 is approximated as smoothstep; exact MT Framework curve is not yet proven")
    for animation in selected_tree:
        target = layout.animation_target(animation)
        if target is None:
            if animation.target_node >= 0:
                warnings.append(
                    f"animation {animation.index} target id {animation.target_node} has no unique node")
            continue
        local_frame = 0 if animation.duration < 0 else min(max(frame, 0), animation.duration)
        state = states[target.index]
        for channel in animation.channels:
            values = _sample_channel(channel, local_frame)
            if values is None:
                continue
            if channel.name in ("position", "rotation", "scale"):
                values = list(values)
                if channel.name == "position" and len(values) >= 2:
                    state["position"] = values[:2]
                elif channel.name == "scale" and len(values) >= 2:
                    state["scale"] = values[:2]
                elif channel.name == "rotation":
                    state["rotation"] = values
            elif channel.name == "geometry_rect" and len(values) >= 4:
                state["geometry"] = list(values[:4])
            elif channel.name == "uv_rect" and len(values) >= 4:
                state["uv"] = list(values[:4])
            elif channel.name == "visibility" and values:
                state["visible"] = bool(values[0])
            elif channel.name == "shake" and values:
                state["shake"] = bool(values[0])
            elif channel.name.startswith("color_") and values:
                ci = int(channel.name.rsplit("_", 1)[1])
                state["colors"][ci] = values[0]
    return states, sorted(set(warnings))

def _mat_mul(a, b):
    aa, ac, atx, ab, ad, aty = a
    ba, bc, btx, bb, bd, bty = b
    return (
        aa * ba + ac * bb,
        aa * bc + ac * bd,
        aa * btx + ac * bty + atx,
        ab * ba + ad * bb,
        ab * bc + ad * bd,
        ab * btx + ad * bty + aty,
    )

def _local_matrix(state):
    x, y = state["position"][:2]
    sx, sy = state["scale"][:2]
    rot = state["rotation"][2] if len(state["rotation"]) >= 3 else 0.0
    r = math.radians(rot)
    c, sn = math.cos(r), math.sin(r)
    return (c * sx, -sn * sy, x, sn * sx, c * sy, y)

def _animated_world_matrix(layout, states, index):
    visiting = set()
    cache = {}
    def walk(i):
        if i < 0:
            return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        if i in cache:
            return cache[i]
        if i in visiting or i >= len(layout.nodes):
            raise ValueError(f"invalid/cyclic PSL parent at node {i}")
        visiting.add(i)
        parent = walk(layout.nodes[i].parent)
        visiting.remove(i)
        value = _mat_mul(parent, _local_matrix(states[i]))
        cache[i] = value
        return value
    return walk(index)

def _transform_point(m, x, y):
    a, c, tx, b, d, ty = m
    return a * x + c * y + tx, b * x + d * y + ty

def _animated_world_transform(layout, states, index):
    m = _animated_world_matrix(layout, states, index)
    x, y = _transform_point(m, 0.0, 0.0)
    sx = math.hypot(m[0], m[3])
    sy = math.hypot(m[1], m[4])
    return x, y, sx, sy

def _animated_bbox(layout, states, index):
    node = layout.nodes[index]
    m = _animated_world_matrix(layout, states, index)
    x0, y0, x1, y1 = states[index]["geometry"]
    pts = [_transform_point(m, x, y) for x, y in
           ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))

def _invert_affine(m):
    a, c, tx, b, d, ty = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError("singular sprite transform")
    return (
        d / det, -c / det, (c * ty - d * tx) / det,
        -b / det, a / det, (b * tx - a * ty) / det,
    )

def _node_alpha(colors):
    return sum((c >> 24) & 0xFF for c in colors) / (4.0 * 255.0)

def _argb_to_rgba(value):
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF,
            value & 0xFF, (value >> 24) & 0xFF)

def _vertex_modulation(size, colors):
    """Bilinear TL/TR/BL/BR AARRGGBB modulation image."""
    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid modulation size {size}")
    tl, tr, bl, br = [_argb_to_rgba(v) for v in colors]
    xvals = [round(255 * i / max(1, w - 1)) for i in range(w)]
    yvals = [round(255 * i / max(1, h - 1)) for i in range(h)]
    xmask = Image.new("L", (w, 1)); xmask.putdata(xvals); xmask = xmask.resize((w, h))
    ymask = Image.new("L", (1, h)); ymask.putdata(yvals); ymask = ymask.resize((w, h))
    top = Image.composite(Image.new("RGBA", size, tr), Image.new("RGBA", size, tl), xmask)
    bottom = Image.composite(Image.new("RGBA", size, br), Image.new("RGBA", size, bl), xmask)
    return Image.composite(bottom, top, ymask)

def _warp_tile(tile, geometry, world_matrix, viewport_scale, output_size):
    out_w, out_h = output_size
    sx, sy = viewport_scale
    gx = (geometry[2] - geometry[0]) / max(1, tile.width)
    gy = (geometry[3] - geometry[1]) / max(1, tile.height)
    source_to_local = (gx, 0.0, geometry[0], 0.0, gy, geometry[1])
    world_to_output = (sx, 0.0, 0.0, 0.0, sy, 0.0)
    source_to_output = _mat_mul(
        world_to_output, _mat_mul(world_matrix, source_to_local))
    inverse = _invert_affine(source_to_output)
    return tile.transform(
        (out_w, out_h), Image.Transform.AFFINE, inverse,
        resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))

def _mask_canvas(arc, layout, states, mask_node, atlas_scale, viewport_scale, output_size):
    """Rasterize a linked type-5 mask; geometry is authoritative fallback."""
    state = states[mask_node.index]
    if not state["visible"]:
        return Image.new("L", output_size, 0)
    geometry = state["geometry"]
    tile = None
    if mask_node.texture:
        try:
            tex_entry = find_entry(arc, mask_node.texture)
            image, _raw = decode_member(arc, tex_entry)
            ux0, uy0, ux1, uy1 = state["uv"]
            rect = tuple(round(v * atlas_scale) for v in (ux0, uy0, ux1, uy1))
            if (0 <= rect[0] < rect[2] <= image.width
                    and 0 <= rect[1] < rect[3] <= image.height):
                tile = image.crop(rect)
        except Exception:
            tile = None
    if tile is None:
        # Some proven type-5 masks use a tiny white resource but derive shape
        # from mAnimSprRect / geometry. A solid local quad is the conservative fallback.
        gw = max(1, abs(geometry[2] - geometry[0]))
        gh = max(1, abs(geometry[3] - geometry[1]))
        tile = Image.new("RGBA", (gw, gh), (255, 255, 255, 255))
    world = _animated_world_matrix(layout, states, mask_node.index)
    warped = _warp_tile(tile, geometry, world, viewport_scale, output_size)
    return warped.getchannel("A")

def _select_rrc_surface(parsed, selector):
    final = parsed["rsx_state"]["surface_clip"]
    if selector == "final":
        return dict(final), {"mode": "final", "draw_count": None}
    if selector == "dominant":
        draws, _writes = _rrc_draw_snapshots(parsed)
        counts = {}
        first = {}
        for draw in draws:
            clip = draw["pipeline"]["surface_clip"]
            key = (clip[0], clip[1], clip[2], clip[3])
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, clip)
        if not counts:
            return dict(final), {"mode": "final-fallback", "draw_count": None}
        key = max(counts, key=lambda k: counts[k])
        clip = first[key]
        return {
            "x": clip[0], "y": clip[1], "width": clip[2], "height": clip[3],
        }, {"mode": "dominant", "draw_count": counts[key]}
    try:
        width, height = map(int, selector.lower().split("x"))
    except Exception as exc:
        raise ValueError("--rrc-surface must be dominant, final, or WxH") from exc
    if width <= 0 or height <= 0:
        raise ValueError("--rrc-surface dimensions must be positive")
    return {"x": 0, "y": 0, "width": width, "height": height}, {
        "mode": "explicit", "draw_count": None}

def cmd_render_layout(args):
    arc = core.parse_arc(Path(args.arc))
    entry, layout = get_layout(arc, args.layout)
    logical_w, logical_h = args.logical_size
    rsx_surface = None
    rsx_surface_selection = None
    if args.rrc:
        parsed_rrc = parse_rrc(Path(args.rrc))
        rsx_surface, rsx_surface_selection = _select_rrc_surface(
            parsed_rrc, args.rrc_surface)
    inferred_output = (
        (rsx_surface["width"], rsx_surface["height"])
        if rsx_surface else args.logical_size
    )
    out_w, out_h = args.output_size or inferred_output
    canvas = Image.new("RGBA", (out_w, out_h), tuple(args.background))
    sx, sy = out_w / logical_w, out_h / logical_h

    if args.animation_root is not None and (
        not layout.animations or layout.animation_parse_error
    ):
        raise ValueError(
            "this layout's animation encoding is not fully decoded: "
            + (layout.animation_parse_error or "unknown variant"))
    root = _resolve_animation_root(layout, args.animation_root)
    states, animation_warnings = _animated_local_states(layout, root, args.frame)

    chosen = []
    wanted = {int(v) for v in args.node} if args.node else None
    needle = args.match.casefold() if args.match else None
    animated_targets = (
        {target.index for a in layout.animation_tree(root.index)
         if (target := layout.animation_target(a)) is not None}
        if root else None
    )
    for node in layout.nodes:
        if node.node_type not in (2, 3) or not node.texture:
            continue
        if root and not args.include_static and node.index not in animated_targets:
            continue
        if wanted is not None and node.index not in wanted:
            continue
        if needle and needle not in node.name.casefold() and needle not in node.texture.casefold():
            continue
        chosen.append(node)

    rendered, skipped = [], []
    for node in chosen:
        try:
            state = states[node.index]
            if not state["visible"]:
                skipped.append({
                    "index": node.index, "name": node.name,
                    "error": "visibility=0 at selected animation state"})
                continue
            alpha = (
                _node_alpha(state["colors"])
                if node.node_type == 2 and (root or args.respect_alpha)
                else 1.0
            )
            if alpha <= 0.0:
                skipped.append({
                    "index": node.index, "name": node.name,
                    "error": "alpha=0 at selected animation/static state"})
                continue

            tex_entry = find_entry(arc, node.texture)
            image, raw = decode_member(arc, tex_entry)
            ux0, uy0, ux1, uy1 = state["uv"]
            x0, y0, x1, y1 = [
                round(v * args.atlas_scale) for v in (ux0, uy0, ux1, uy1)]
            if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                raise ValueError(f"source rect {(x0, y0, x1, y1)} outside {image.size}")
            tile = image.crop((x0, y0, x1, y1))
            dx0, dy0, dx1, dy1 = _animated_bbox(layout, states, node.index)
            px0, py0 = round(dx0 * sx), round(dy0 * sy)
            px1, py1 = round(dx1 * sx), round(dy1 * sy)
            if px1 <= px0 or py1 <= py0:
                raise ValueError(f"invalid destination box {(px0, py0, px1, py1)}")
            if node.node_type == 3:
                tile = ImageChops.multiply(tile, _vertex_modulation(tile.size, state["colors"]))
            elif alpha < 0.999:
                tile.putalpha(tile.getchannel("A").point(
                    lambda v: max(0, min(255, round(v * alpha)))))

            local_to_world = _animated_world_matrix(layout, states, node.index)
            warped = _warp_tile(
                tile, state["geometry"], local_to_world, (sx, sy), (out_w, out_h))

            mask_node = layout.mask_for(node.index)
            mask_applied = None
            if mask_node is not None:
                mask = _mask_canvas(
                    arc, layout, states, mask_node, args.atlas_scale,
                    (sx, sy), (out_w, out_h))
                warped.putalpha(ImageChops.multiply(warped.getchannel("A"), mask))
                mask_applied = mask_node.index

            canvas.alpha_composite(warped)
            rendered.append({
                **node_info(layout, node, args.atlas_scale),
                "animated_geometry": list(state["geometry"]),
                "animated_uv_logical": list(state["uv"]),
                "animated_position": list(state["position"]),
                "animated_scale": list(state["scale"]),
                "animated_rotation": list(state["rotation"]),
                "animated_visible": state["visible"],
                "animated_shake": state["shake"],
                "alpha": alpha,
                "vertex_modulation": node.node_type == 3,
                "mask_applied": mask_applied,
                "texture_member": tex_entry.name,
                "texture_sha256": sha256(raw),
                "dest_bbox_logical_animated": [dx0, dy0, dx1, dy1],
                "dest_bbox_output": [px0, py0, px1, py1],
            })
        except Exception as exc:
            skipped.append({"index": node.index, "name": node.name, "error": str(exc)})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(json.dumps({
        "archive": args.arc, "archive_sha256": arc.data_sha256,
        "layout": entry.name, "logical_size": list(args.logical_size),
        "output_size": [out_w, out_h], "atlas_scale": args.atlas_scale,
        "rsx_surface": rsx_surface,
        "rsx_surface_selection": rsx_surface_selection,
        "animation_root": (
            {"index": root.index, "name": root.name, "frame": args.frame}
            if root else None),
        "animation_warnings": animation_warnings,
        "rendered": rendered, "skipped": skipped, "out": str(out),
    }, indent=2, ensure_ascii=False))


def build_cli():
    ap = argparse.ArgumentParser(description="BASARA 3 Utage offline verification / partial 2D runtime harness")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("arc-report"); p.add_argument("arc"); p.add_argument("--json"); p.set_defaults(func=cmd_arc_report)
    p = sp.add_parser("preview"); p.add_argument("arc"); p.add_argument("member"); p.add_argument("out"); p.set_defaults(func=cmd_preview)
    p = sp.add_parser("compare-arcs"); p.add_argument("a"); p.add_argument("b"); p.set_defaults(func=cmd_compare)
    p = sp.add_parser("layouts"); p.add_argument("arc"); p.set_defaults(func=cmd_layouts)
    p = sp.add_parser("layout-nodes"); p.add_argument("arc"); p.add_argument("--layout")
    p.add_argument("--match"); p.add_argument("--atlas-scale", type=float, default=2.0)
    p.set_defaults(func=cmd_layout_nodes)
    p = sp.add_parser("psl-sweep"); p.add_argument("root"); p.add_argument("--json")
    p.set_defaults(func=cmd_psl_sweep)
    p = sp.add_parser("layout-animations"); p.add_argument("arc"); p.add_argument("--layout")
    p.add_argument("--root"); p.add_argument("--match")
    p.set_defaults(func=cmd_layout_animations)
    p = sp.add_parser("render-layout"); p.add_argument("arc"); p.add_argument("out")
    p.add_argument("--layout"); p.add_argument("--match"); p.add_argument("--node", action="append")
    p.add_argument("--atlas-scale", type=float, default=2.0)
    p.add_argument("--logical-size", type=lambda s: tuple(map(int, s.lower().split("x"))), default=(640, 480))
    p.add_argument("--output-size", type=lambda s: tuple(map(int, s.lower().split("x"))))
    p.add_argument("--background", type=lambda s: tuple(map(int, s.split(","))), default=(0, 0, 0, 0))
    p.add_argument("--animation-root", help="animation record index or unique name fragment; ambiguous container roots fail closed")
    p.add_argument("--frame", type=int, default=0)
    p.add_argument("--respect-alpha", action="store_true")
    p.add_argument("--include-static", action="store_true",
                   help="with --animation-root, also draw textured nodes outside that animation tree")
    p.add_argument("--rrc", help="use an RRC capture to select an RSX output surface")
    p.add_argument("--rrc-surface", default="dominant",
                   help="RRC surface selection: dominant (default), final, or WxH")
    p.set_defaults(func=cmd_render_layout)
    p = sp.add_parser("render-scene"); p.add_argument("scene"); p.add_argument("out"); p.set_defaults(func=cmd_render_scene)
    p = sp.add_parser("rrc-info"); p.add_argument("capture"); p.set_defaults(func=cmd_rrc_info)
    p = sp.add_parser("rrc-state"); p.add_argument("capture"); p.set_defaults(func=cmd_rrc_state)
    p = sp.add_parser("rrc-draws"); p.add_argument("capture")
    p.add_argument("--unique", action="store_true"); p.add_argument("--writes", action="store_true")
    p.add_argument("--limit", type=int); p.set_defaults(func=cmd_rrc_draws)
    p = sp.add_parser("rrc-match-arc"); p.add_argument("capture"); p.add_argument("arc"); p.set_defaults(func=cmd_rrc_match_arc)
    return ap

def main():
    args = build_cli().parse_args()
    try: args.func(args); return 0
    except Exception as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr); return 2

if __name__ == "__main__":
    raise SystemExit(main())
