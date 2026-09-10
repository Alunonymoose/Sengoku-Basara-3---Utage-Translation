import struct
from build_v5 import *
def extend_font(source):
 oldtnf=arc.unpack(source.entries[0]);oldcsa=arc.unpack(source.entries[24]);oldpage=arc.unpack(source.entries[23]);tnf=bytearray(oldtnf);csa=bytearray(oldcsa);page=oldpage
 donor=arc.parse_arc(ROM/'eng/tenka/tenka_id.arc');dt=arc.unpack(donor.entries[0]);dc=arc.unpack(donor.entries[18]);dh=struct.unpack_from('>I',dt,16)[0];count=struct.unpack_from('>I',tnf,8)[0]
 for off,(ch,x,width) in enumerate([('K',312,13),('j',352,5)]):
  # Prove these new cells do not intersect any existing glyph sampling rectangle.
  rect=(x,440,x+width*2,492)
  for i in range(count):
   gid,u,v,w=struct.unpack_from('>4H',oldtnf,32+8*i)
   if gid>>8==20:assert not (u*2<rect[2] and (u+w)*2>rect[0] and v*2<rect[3] and v*2+52>rect[1])
  di=struct.unpack_from('>H',dc,8+ord(ch)*2)[0];gid,u,v,w=struct.unpack_from('>4H',dt,32+di*8);di=unpack_color(decode(arc.unpack(donor.entries[3+(gid>>8)])));s=di.crop((u*2,v*2,(u+w)*2,v*2+52))
  # The smaller donor glyphs include a black matte. Extract their visible ink,
  # then align the cap height/baseline to the existing 26-point shop alphabet.
  pixels=np.array(s);pixels[pixels[:,:,:3].max(2)<20,3]=0;s=Image.fromarray(pixels);s=s.crop(s.getbbox()).resize((width*2,34 if ch=='K' else 40),Image.Resampling.LANCZOS)
  cw=32 if ch=='K' else 24;c=Image.new('RGBA',(cw,52));c.alpha_composite(s,(0,9));page=paint(page,c,(x,440,x+cw,492))
  tnf+=struct.pack('>4H',(20<<8)+79+off,x//2,220,width);struct.pack_into('>H',csa,8+ord(ch)*2,count+off)
 struct.pack_into('>I',tnf,8,count+2)
 return {oldtnf:bytes(tnf),oldcsa:bytes(csa),oldpage:page}
