from __future__ import annotations
import importlib.util
import struct
import zlib
from pathlib import Path

from hypothesis import given, settings, strategies as st

REPO=Path(__file__).resolve().parents[3]
SAFE=REPO/"project/tools/donor_matcher_v5_1_2026-09-23/safe_arc.py"
spec=importlib.util.spec_from_file_location("safe_arc_property",SAFE)
safe=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(safe)


def build_arc(items):
    count=len(items); table_end=8+80*count; cursor=(table_end+15)&~15
    records=[]; payloads=[]
    for i,(compressed,raw) in enumerate(items):
        stored=zlib.compress(raw,9) if compressed else raw
        off=cursor; payloads.append((off,stored)); cursor=(off+len(stored)+15)&~15
        rec=bytearray(80); name=f"id\\fixture\\entry_{i:02d}".encode("ascii"); rec[:len(name)]=name
        struct.pack_into(">IIII",rec,64,0x242BB29A,len(stored),len(raw)<<3,off); records.append(bytes(rec))
    out=bytearray(cursor); out[:4]=b"\0CRA"; struct.pack_into(">HH",out,4,8,count)
    for i,rec in enumerate(records): out[8+i*80:8+(i+1)*80]=rec
    for off,stored in payloads: out[off:off+len(stored)]=stored
    return bytes(out)


payload=st.binary(min_size=0,max_size=63)
items=st.lists(st.tuples(st.booleans(),payload),min_size=2,max_size=8).map(
    lambda xs:[(compressed,(data if compressed else b"R"+data) or b"Z") for compressed,data in xs]
)


@settings(max_examples=100,deadline=None)
@given(items)
def test_noop_rebuild_is_exact(xs):
    arc=build_arc(xs)
    assert safe.rebuild_arc(arc,{})==arc
    evidence=safe.verify_rebuild(arc,arc,{})
    assert evidence["changed_member_count"]==0


@settings(max_examples=100,deadline=None)
@given(items)
def test_same_length_replacement_preserves_every_untouched_stored_member(xs):
    arc=build_arc(xs); before=safe.parse_arc(arc)
    idx=len(xs)//2; old=before[idx]["raw"]
    replacement=(b"Q"*len(old)) if old else b"Q"
    if len(replacement)!=len(old):
        # Generated fixtures always have non-empty raw payloads; defensive only.
        return
    out=safe.rebuild_arc(arc,{idx:replacement}); after=safe.parse_arc(out)
    assert after[idx]["raw"]==replacement
    for i,(a,b) in enumerate(zip(before,after)):
        if i==idx: continue
        assert a["stored"]==b["stored"]
        assert a["packed_size"]==b["packed_size"]
        assert a["record"][:68]==b["record"][:68]
