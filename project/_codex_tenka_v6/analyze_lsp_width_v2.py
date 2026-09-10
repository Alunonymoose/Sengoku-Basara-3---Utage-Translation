from __future__ import annotations

import struct

import analyze_lsp_width as base


def read_string(data: bytes, cursor: int) -> tuple[str, int]:
    length = struct.unpack_from(">I", data, cursor)[0]
    start = cursor + 4
    end = start + length
    if length < 1 or end > len(data):
        raise ValueError(f"bad string at 0x{cursor:X}: {length}")
    value = data[start:end].rstrip(b"\0").decode("ascii", "replace")
    return value, end


if __name__ == "__main__":
    base.read_string = read_string
    base.main()
