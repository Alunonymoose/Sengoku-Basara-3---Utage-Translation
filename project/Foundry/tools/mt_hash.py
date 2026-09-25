#!/usr/bin/env python3
"""MT Framework V2 resource-class hash helper.

For the SB3 / Samurai Heroes ARC family, resource class hashes such as
rTexture -> 0x241F5DEB are CRC32B-derived and masked to 31 bits.

Algorithm corroborated against RevilLib MTHashV2 and known ARC hashes:
    hash = (~crc32(text_bytes)) & 0x7fffffff

This tool does not guess class names. It hashes supplied candidates and can
compare them with a target ARC type hash.
"""

from __future__ import annotations

import argparse
import zlib


def mt_hash_v2(text: str) -> int:
    return (~zlib.crc32(text.encode("utf-8"))) & 0x7FFFFFFF


def parse_hash(value: str) -> int:
    return int(value, 0) & 0xFFFFFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", help="resource class names, e.g. rTexture")
    parser.add_argument("--target", help="optional hash to match, e.g. 0x241F5DEB")
    args = parser.parse_args()

    target = parse_hash(args.target) if args.target else None

    for name in args.names:
        value = mt_hash_v2(name)
        marker = " MATCH" if target is not None and value == target else ""
        print(f"{name}\t0x{value:08X}{marker}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
