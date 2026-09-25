"""MT Framework V2 resource-class hashes: (~crc32(name)) & 0x7fffffff."""
from __future__ import annotations

import zlib


def mt_hash(name: str) -> int:
    return (~zlib.crc32(name.encode("utf-8"))) & 0x7FFFFFFF


# Only hashes proven against real archives belong here.
R_TEXTURE = 0x241F5DEB
KNOWN = {R_TEXTURE: "rTexture"}


def label(type_hash: int) -> str:
    return KNOWN.get(type_hash, f"0x{type_hash:08X}")
