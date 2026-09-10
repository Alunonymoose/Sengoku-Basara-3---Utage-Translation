import sys,struct
from pathlib import Path
sys.path.insert(0,r'E:\Utage Patching New\_codex_select_menu\quest_v3')
from common import np,xet_info
from build_free_battle_v6 import encode_bc3_block,rgb_to_565,rgb_from_565

def encode_block(ps):
 # XET uses BC3 alpha as luminance; never cull colour/opacity by that channel.
 ab=encode_bc3_block(ps)[:8]
 rgb=[p[:3] for p in ps]
 low=min(rgb,key=lambda c:c[0]*3+c[1]*6+c[2]);high=max(rgb,key=lambda c:c[0]*3+c[1]*6+c[2])
 c0,c1=rgb_to_565(high),rgb_to_565(low)
 # Preserve both endpoint colours. The old encoder replaced one with the other +1.
 if c0<c1:c0,c1=c1,c0
 a,b=rgb_from_565(c0),rgb_from_565(c1)
 if any(p[1]==0 for p in rgb) and min(a[1],b[1])>0:
  bg=rgb_to_565(next(p for p in rgb if p[1]==0))
  if a[1]<b[1]:c0=bg
  else:c1=bg
  if c0<c1:c0,c1=c1,c0
  a,b=rgb_from_565(c0),rgb_from_565(c1)
 palette=[a,b,tuple((2*x+y)//3 for x,y in zip(a,b)),tuple((x+2*y)//3 for x,y in zip(a,b))]
 bits=0
 for i,p in enumerate(rgb):
  k=min(range(4),key=lambda k:palette[k][1]) if p[1]==0 else min(range(4),key=lambda k:sum((p[c]-palette[k][c])**2 for c in range(3)))
  bits|=k<<(2*i)
 return ab+struct.pack('<HHI',c0,c1,bits)

def patch_bc3_rect(raw,image,rect):
 inf=xet_info(raw);b=bytearray(raw);px=image.load();x0,y0,x1,y1=rect
 assert all(v%4==0 for v in rect)
 for by in range(y0//4,y1//4):
  for bx in range(x0//4,x1//4):
   ps=[px[bx*4+x,by*4+y] for y in range(4) for x in range(4)]
   off=inf['texture_offset']+(by*(inf['width']//4)+bx)*16;b[off:off+16]=encode_block(ps)
 return bytes(b)
