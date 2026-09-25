from __future__ import annotations
import struct
from core import sha256_bytes


def inspect_arc(data: bytes, safe_arc):
    """Read-only ARC index parser that tolerates non-zero gaps/trailers.

    Header/version/range/codec/overlap checks remain strict. Production writes
    must continue through certified safe_arc.parse_arc()/rebuild_arc().
    """
    if not isinstance(data, bytes):
        raise TypeError("ARC input must be immutable bytes")
    if len(data)<8 or data[:4]!=b"\0CRA":
        raise ValueError("expected PS3 big-endian ARC header")
    version,count=struct.unpack_from(">HH",data,4)
    if version!=8: raise ValueError(f"unsupported ARC version: {version}")
    entry_size=safe_arc.ENTRY_SIZE
    table_end=8+count*entry_size
    if table_end>len(data): raise ValueError("ARC entry table exceeds source")
    entries=[]
    for index in range(count):
        start=8+index*entry_size; record=data[start:start+entry_size]
        type_hash,size,packed,offset=struct.unpack_from(">IIII",record,64)
        if offset<table_end or offset+size>len(data):
            raise ValueError(f"member {index}: payload range outside ARC")
        name=record[:64].split(b"\0",1)[0].decode("utf-8",errors="replace")
        stored=data[offset:offset+size]
        raw,codec,warning=safe_arc._decode(stored,packed>>3,index)
        entries.append(dict(index=index,name=name,type_hash=type_hash,
            compressed_size=size,raw_size=packed>>3,flags=packed&7,
            packed_size=packed,payload_offset=offset,record=record,stored=stored,
            raw=raw,codec=codec,warning=warning))
    anomalies=[]; cursor=table_end
    for entry in sorted(entries,key=lambda e:(e["payload_offset"],e["index"])):
        offset=entry["payload_offset"]
        if offset<cursor: raise ValueError(f"member {entry['index']}: overlapping payloads")
        gap=data[cursor:offset]
        if any(gap):
            anomalies.append({"kind":"nonzero_gap","start":cursor,"end":offset,"size":len(gap),"sha256":sha256_bytes(gap)})
        cursor=offset+entry["compressed_size"]
    trailer=data[cursor:]
    if any(trailer):
        anomalies.append({"kind":"nonzero_trailer","start":cursor,"end":len(data),"size":len(trailer),"sha256":sha256_bytes(trailer)})
    return entries,anomalies
