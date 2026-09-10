#!/usr/bin/env python3
"""Run the V19 read-only diagnostic with stable selection for duplicate Line_U."""

from __future__ import annotations

import struct

import diagnose_v19_text_alignment as D


original = D.V18.stable_node_id


def stable_node_id(raw: bytes, wanted_name: str) -> tuple[int, int]:
    if wanted_name != "Line_U":
        return original(raw, wanted_name)
    _, names = D.V18.node_names(raw)
    hits = []
    for index, name in enumerate(names):
        if name != wanted_name:
            continue
        node_id = struct.unpack_from(">I", raw, D.V18.NODE0 + index * D.V18.NODE_SIZE + 0x50)[0]
        if node_id == 77:
            hits.append((index, node_id))
    if len(hits) != 1:
        raise AssertionError({"Line_U stable ID 77 hits": hits})
    return hits[0]


D.V18.stable_node_id = stable_node_id
D.main()
