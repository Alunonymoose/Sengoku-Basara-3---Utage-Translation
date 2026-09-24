"""Recovered standalone XET decoder/validator for Sengoku BASARA 3 Utage PS3.

Evidence source: BASARA Foundry, 2026-09-23 solved XET contract.
Read-only tool. No production encoding claims.

Supported observed formats under the current fixture-backed corpus contract:
  0x15 -> BC2/DXT3 (real Utage fixture + Kuriimu2 table, 2026-09-22)
  0x2A / 0x17 / 0x18 -> BC3/DXT5
  0x19 -> BC1/DXT1
  0x27 -> A8R8G8B8

PS3 BC block quirk: RGB565 endpoints are big-endian u16; index byte arrays
retain standard little-endian bit packing.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import List

MAGIC=b"\x00XET"
BC2_FORMATS={0x15}
BC3_FORMATS={0x2A,0x17,0x18}
BC1_FORMATS={0x19}
ARGB_FORMATS={0x27}

@dataclass(frozen=True)
class XetInfo:
    version_flags:int
    tex_flags:int
    flags:int
    mip_count:int
    width:int
    height:int
    format_id:int
    mip_offsets:tuple[int,...]

def xet_info(raw:bytes)->XetInfo:
    if not isinstance(raw,(bytes,bytearray,memoryview)):
        raise TypeError('raw must be bytes-like')
    raw=bytes(raw)
    if len(raw)<20 or raw[:4]!=MAGIC:
        raise ValueError('not a PS3 XET resource')
    vf, tf, flags = struct.unpack_from('>III', raw, 4)
    mip=tf & 0x3F
    width=(tf>>6)&0x1FFF
    height=(tf>>19)&0x1FFF
    if mip<1 or width<1 or height<1:
        raise ValueError(f'invalid dimensions/mips: {width}x{height} mip={mip}')
    table_end=16+4*mip
    if table_end>len(raw):
        raise ValueError('mip offset table exceeds resource')
    offs=tuple(struct.unpack_from('>I',raw,16+4*i)[0] for i in range(mip))
    if any(o<table_end or o>=len(raw) for o in offs):
        raise ValueError(f'invalid mip offsets: {offs}')
    if tuple(sorted(offs))!=offs:
        raise ValueError('mip offsets are not ascending')
    fmt=raw[0x0E]
    return XetInfo(vf,tf,flags,mip,width,height,fmt,offs)

def _rgb565_be(buf:bytes,off:int):
    v=struct.unpack_from('>H',buf,off)[0]
    r=(v>>11)&31; g=(v>>5)&63; b=v&31
    return ((r*255+15)//31,(g*255+31)//63,(b*255+15)//31)

def _decode_bc1_block(block:bytes, force_four:bool=False):
    if len(block)!=8: raise ValueError('BC1 block size')
    v0=struct.unpack_from('>H',block,0)[0]; v1=struct.unpack_from('>H',block,2)[0]
    c0=_rgb565_be(block,0); c1=_rgb565_be(block,2)
    if force_four or v0>v1:
        pal=[c0,c1,
             tuple((2*c0[i]+c1[i])//3 for i in range(3)),
             tuple((c0[i]+2*c1[i])//3 for i in range(3))]
        alpha=[255]*4
    else:
        pal=[c0,c1,tuple((c0[i]+c1[i])//2 for i in range(3)),(0,0,0)]
        alpha=[255,255,255,0]
    idx=int.from_bytes(block[4:8],'little')
    out=[]
    for t in range(16):
        p=(idx>>(2*t))&3
        out.append((*pal[p],alpha[p]))
    return out

def _decode_bc2_block(block:bytes):
    if len(block)!=16: raise ValueError('BC2 block size')
    alpha_bits=int.from_bytes(block[:8],'little')
    colors=_decode_bc1_block(block[8:16], force_four=True)
    out=[]
    for t,(r,g,b,_) in enumerate(colors):
        a=((alpha_bits>>(4*t))&0xF)*17
        out.append((r,g,b,a))
    return out

def _alpha_palette(a0:int,a1:int):
    if a0>a1:
        return [a0,a1,
                (6*a0+1*a1)//7,(5*a0+2*a1)//7,(4*a0+3*a1)//7,
                (3*a0+4*a1)//7,(2*a0+5*a1)//7,(1*a0+6*a1)//7]
    return [a0,a1,
            (4*a0+1*a1)//5,(3*a0+2*a1)//5,(2*a0+3*a1)//5,(1*a0+4*a1)//5,
            0,255]

def _decode_bc3_block(block:bytes):
    if len(block)!=16: raise ValueError('BC3 block size')
    ap=_alpha_palette(block[0],block[1])
    aidx=int.from_bytes(block[2:8],'little')
    colors=_decode_bc1_block(block[8:16], force_four=True)
    out=[]
    for t,(r,g,b,_) in enumerate(colors):
        a=ap[(aidx>>(3*t))&7]
        out.append((r,g,b,a))
    return out

def _surface_extent(fmt:int,w:int,h:int)->int:
    if fmt in BC2_FORMATS or fmt in BC3_FORMATS:
        return ((w+3)//4)*((h+3)//4)*16
    if fmt in BC1_FORMATS:
        return ((w+3)//4)*((h+3)//4)*8
    if fmt in ARGB_FORMATS:
        return w*h*4
    raise ValueError(f'unsupported XET format 0x{fmt:02X}')

def validate(raw:bytes)->dict:
    info=xet_info(raw)
    levels=[]
    for level,o in enumerate(info.mip_offsets):
        w=max(1,info.width>>level); h=max(1,info.height>>level)
        need=_surface_extent(info.format_id,w,h)
        end=o+need
        next_o=info.mip_offsets[level+1] if level+1<info.mip_count else len(raw)
        if end>len(raw):
            raise ValueError(f'mip {level} payload exceeds resource')
        if end>next_o:
            raise ValueError(f'mip {level} overlaps next mip')
        levels.append({'level':level,'width':w,'height':h,'offset':o,'bytes':need,
                       'padding_to_next':next_o-end})
    return {'width':info.width,'height':info.height,'mip_count':info.mip_count,
            'format_id':info.format_id,'levels':levels,'resource_bytes':len(raw)}

def decode_rgba(raw:bytes,level:int=0)->bytes:
    info=xet_info(raw)
    if not (0<=level<info.mip_count): raise ValueError('bad mip level')
    w=max(1,info.width>>level); h=max(1,info.height>>level); off=info.mip_offsets[level]
    need=_surface_extent(info.format_id,w,h)
    src=raw[off:off+need]
    out=bytearray(w*h*4)
    if info.format_id in ARGB_FORMATS:
        for i in range(w*h):
            a,r,g,b=src[i*4:i*4+4]
            out[i*4:i*4+4]=bytes((r,g,b,a))
        return bytes(out)
    if info.format_id in BC2_FORMATS:
        bs=16; dec=_decode_bc2_block
    elif info.format_id in BC3_FORMATS:
        bs=16; dec=_decode_bc3_block
    else:
        bs=8; dec=_decode_bc1_block
    p=0
    for by in range((h+3)//4):
        for bx in range((w+3)//4):
            px=dec(src[p:p+bs]); p+=bs
            for iy in range(4):
                y=by*4+iy
                if y>=h: continue
                for ix in range(4):
                    x=bx*4+ix
                    if x>=w: continue
                    out[(y*w+x)*4:(y*w+x+1)*4]=bytes(px[iy*4+ix])
    return bytes(out)

if __name__=='__main__':
    import argparse, pathlib, json
    ap=argparse.ArgumentParser()
    ap.add_argument('xet')
    ap.add_argument('--level',type=int,default=0)
    ap.add_argument('--raw-rgba')
    ns=ap.parse_args()
    raw=pathlib.Path(ns.xet).read_bytes()
    print(json.dumps(validate(raw),indent=2))
    if ns.raw_rgba:
        pathlib.Path(ns.raw_rgba).write_bytes(decode_rgba(raw,ns.level))
