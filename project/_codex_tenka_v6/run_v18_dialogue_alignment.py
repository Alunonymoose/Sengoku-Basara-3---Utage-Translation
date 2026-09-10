#!/usr/bin/env python3
"""Run V18 with duplicate node names resolved by their stable IDs."""

from __future__ import annotations

import struct

import build_v18_dialogue_alignment as v18


def stable_node_id(raw: bytes, wanted_name: str) -> tuple[int, int]:
    _, names = v18.node_names(raw)
    expected_ids = {"Line_U": 77}
    candidates = []
    for index, name in enumerate(names):
        if name != wanted_name:
            continue
        node_id = struct.unpack_from(
            ">I", raw, v18.NODE0 + index * v18.NODE_SIZE + 0x50
        )[0]
        if wanted_name in expected_ids and node_id != expected_ids[wanted_name]:
            continue
        candidates.append((index, node_id))
    if len(candidates) != 1:
        raise AssertionError(f"node {wanted_name!r}: found {candidates}")
    return candidates[0]


v18.stable_node_id = stable_node_id
v18.main()
