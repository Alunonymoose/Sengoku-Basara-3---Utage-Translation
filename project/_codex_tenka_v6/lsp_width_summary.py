from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import analyze_lsp_width as base


def read_string(data: bytes, cursor: int) -> tuple[str, int]:
    length = struct.unpack_from(">I", data, cursor)[0]
    start = cursor + 4
    end = start + length
    if length < 1 or end > len(data):
        raise ValueError((cursor, length))
    return data[start:end].rstrip(b"\0").decode("ascii", "replace"), end


def summarize(path: Path) -> dict:
    base.read_string = read_string
    result = base.parse(path)
    nodes = result["nodes"]
    selected = []
    for node in nodes:
        if node["name"] != "St_s":
            continue
        parent = nodes[node["parent"]] if node["parent"] >= 0 else None
        selected.append({
            "index": node["index"],
            "parent_index": node["parent"],
            "parent_name": parent["name"] if parent else "",
            "position": [node["floats"]["0x00"], node["floats"]["0x04"]],
            "float_08_34": [node["floats"][f"0x{o:02X}"] for o in range(0x08, 0x38, 4)],
            "size_48_4c": [node["ints"]["0x48"], node["ints"]["0x4C"]],
            "material": node["ints"]["0x60"],
            "geometry": [node["ints"][f"0x{o:02X}"] for o in (0x74, 0x78, 0x7C, 0x80)],
            "uv": [node["ints"][f"0x{o:02X}"] for o in (0x84, 0x88, 0x8C, 0x90)],
        })
    return {
        "path": str(path),
        "node_count": result["node_count"],
        "aux_count": result["aux_count"],
        "pre_name_size": result["pre_name_size"],
        "tail_name_count": len(result["tail_names"]),
        "st_s": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([summarize(path) for path in args.paths], indent=2))


if __name__ == "__main__":
    main()
