#!/usr/bin/env python3
"""Utage Harness: BASARA-specific offline verifier / partial 2D runtime.

This is deliberately not a PS3 emulator. It reuses current BASARA Foundry
parsers/codecs, renders known 2D composition contracts, and correlates RPCS3
RRC v6 active memory with exact live ARC members.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, struct, sys
from collections import Counter
from pathlib import Path
from typing import Iterable
from PIL import Image

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
    for _ in range(r.vle()): r.raw(132); r.u64()
    active = set(); commands = r.vle()
    for _ in range(commands):
        r.u32(); r.u32()
        for _ in range(r.vle()): active.add(r.u64())
        r.u64(); r.u64()
    states = {blocks[h][2] for h in active if h in blocks}
    return {"version": version, "commands": commands, "blocks": blocks,
            "payloads": payloads, "active_blocks": active, "active_states": states,
            "decompressed_size": len(raw), "reg_state_offset": r.p}

def cmd_rrc_info(args):
    p = parse_rrc(Path(args.capture))
    active_bytes = sum(len(p["payloads"][s]) for s in p["active_states"])
    out = {"capture": args.capture, "version": p["version"], "replay_commands": p["commands"],
           "memory_blocks": len(p["blocks"]), "payloads_total": len(p["payloads"]),
           "active_blocks": len(p["active_blocks"]), "active_unique_payloads": len(p["active_states"]),
           "active_payload_bytes": active_bytes, "reg_state_offset": p["reg_state_offset"],
           "opaque_tail_bytes": p["decompressed_size"] - p["reg_state_offset"]}
    print(json.dumps(out, indent=2))

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
        "index": node.index, "name": node.name, "role": node.role,
        "type": node.node_type, "parent": node.parent, "texture": node.texture,
        "position": list(node.position), "scale": list(node.scale),
        "geometry": list(node.geometry), "uv_logical": list(node.uv),
        "source_rect_physical": list(node.source_rect(atlas_scale)),
        "world_transform": list(layout.world_transform(node.index)),
        "dest_bbox_logical": list(layout.logical_bbox(node.index)),
        "material": node.material,
    }

def cmd_layouts(args):
    arc = core.parse_arc(Path(args.arc))
    out = []
    for x in lsp.layouts_in_archive(arc):
        out.append({"member": x.name, "version": x.version, "declared_nodes": x.node_count,
                    "recovered_nodes": len(x.nodes), "textures": x.textures,
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

def cmd_render_layout(args):
    arc = core.parse_arc(Path(args.arc))
    entry, layout = get_layout(arc, args.layout)
    logical_w, logical_h = args.logical_size
    out_w, out_h = args.output_size or args.logical_size
    canvas = Image.new("RGBA", (out_w, out_h), tuple(args.background))
    sx, sy = out_w / logical_w, out_h / logical_h
    chosen = []
    wanted = {int(v) for v in args.node} if args.node else None
    needle = args.match.casefold() if args.match else None
    for node in layout.nodes:
        if node.node_type != 2 or not node.texture:
            continue
        if wanted is not None and node.index not in wanted:
            continue
        if needle and needle not in node.name.casefold() and needle not in node.texture.casefold():
            continue
        chosen.append(node)

    rendered, skipped = [], []
    for node in chosen:
        try:
            tex_entry = find_entry(arc, node.texture)
            image, raw = decode_member(arc, tex_entry)
            x0, y0, x1, y1 = node.source_rect(args.atlas_scale)
            if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                raise ValueError(f"source rect {(x0, y0, x1, y1)} outside {image.size}")
            tile = image.crop((x0, y0, x1, y1))
            dx0, dy0, dx1, dy1 = layout.logical_bbox(node.index)
            px0, py0 = round(dx0 * sx), round(dy0 * sy)
            px1, py1 = round(dx1 * sx), round(dy1 * sy)
            if px1 <= px0 or py1 <= py0:
                raise ValueError(f"invalid destination box {(px0, py0, px1, py1)}")
            tile = tile.resize((px1 - px0, py1 - py0), Image.Resampling.BICUBIC)
            canvas.alpha_composite(tile, (px0, py0))
            rendered.append({
                **node_info(layout, node, args.atlas_scale),
                "texture_member": tex_entry.name,
                "texture_sha256": sha256(raw),
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
    p = sp.add_parser("render-layout"); p.add_argument("arc"); p.add_argument("out")
    p.add_argument("--layout"); p.add_argument("--match"); p.add_argument("--node", action="append")
    p.add_argument("--atlas-scale", type=float, default=2.0)
    p.add_argument("--logical-size", type=lambda s: tuple(map(int, s.lower().split("x"))), default=(640, 480))
    p.add_argument("--output-size", type=lambda s: tuple(map(int, s.lower().split("x"))))
    p.add_argument("--background", type=lambda s: tuple(map(int, s.split(","))), default=(0, 0, 0, 0))
    p.set_defaults(func=cmd_render_layout)
    p = sp.add_parser("render-scene"); p.add_argument("scene"); p.add_argument("out"); p.set_defaults(func=cmd_render_scene)
    p = sp.add_parser("rrc-info"); p.add_argument("capture"); p.set_defaults(func=cmd_rrc_info)
    p = sp.add_parser("rrc-match-arc"); p.add_argument("capture"); p.add_argument("arc"); p.set_defaults(func=cmd_rrc_match_arc)
    return ap

def main():
    args = build_cli().parse_args()
    try: args.func(args); return 0
    except Exception as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr); return 2

if __name__ == "__main__":
    raise SystemExit(main())
