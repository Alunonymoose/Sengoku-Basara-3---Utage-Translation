"""PSL layout (read-only). Fixture-proven fields only:

header 0x10 bytes: +4 u32 version, +0x0C u16 record count, +0x0E u16 secondary count;
records 0xB0 bytes: +0x00/+0x04 f32 x/y, +0x38 u32 parent (0xFFFFFFFF = root),
+0x50 u32 node binding id, +0x74..+0x80 f32 destination rect (x0,y0,x1,y1),
+0x84..+0x90 f32 source rect (x0,y0,x1,y1). ``_ID_HQ`` textures map at 2x the
SD source coordinates on proven fixtures (not universal).

Which GSM/FIM row a node consumes is NOT derivable from these fields.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

PSL_MAGIC = b"\x00PSL"
HEADER_SIZE = 0x10
RECORD_SIZE = 0xB0


class PslError(ValueError):
    pass


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def scaled(self, k: float) -> "Rect":
        return Rect(self.x0 * k, self.y0 * k, self.x1 * k, self.y1 * k)


@dataclass(frozen=True)
class Node:
    index: int
    x: float
    y: float
    parent: Optional[int]
    binding_id: int
    dest: Rect
    source: Rect


@dataclass(frozen=True)
class Psl:
    version: int
    nodes: tuple[Node, ...]

    @classmethod
    def parse(cls, raw: bytes) -> "Psl":
        if len(raw) < HEADER_SIZE or raw[:4] != PSL_MAGIC:
            raise PslError("not a PSL layout")
        version = struct.unpack_from(">I", raw, 4)[0]
        count = struct.unpack_from(">H", raw, 12)[0]
        if HEADER_SIZE + count * RECORD_SIZE > len(raw):
            raise PslError("record array overruns resource")
        nodes = []
        for i in range(count):
            o = HEADER_SIZE + i * RECORD_SIZE
            parent = struct.unpack_from(">I", raw, o + 0x38)[0]
            if parent != 0xFFFFFFFF and parent >= count:
                raise PslError(f"node {i}: parent {parent} out of range")
            f = lambda off: struct.unpack_from(">4f", raw, o + off)
            nodes.append(Node(i, *struct.unpack_from(">2f", raw, o),
                              None if parent == 0xFFFFFFFF else parent,
                              struct.unpack_from(">I", raw, o + 0x50)[0],
                              Rect(*f(0x74)), Rect(*f(0x84))))
        return cls(version, tuple(nodes))

    def children(self, index: int) -> list[Node]:
        return [n for n in self.nodes if n.parent == index]
