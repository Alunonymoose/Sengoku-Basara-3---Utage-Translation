from build_v5 import *
a=arc.parse_arc(ROM/'eng/title.arc');im=unpack_color(decode(arc.unpack(a.entries[324])));buttons=unpack_color(decode(arc.unpack(a.entries[299])))
# Reconstruct the three native compact-footer nodes at 4x screen scale.
canvas=Image.new('RGBA',(600,180),(58,61,57,255));scale=4
for rect,pos,geom in [((768,192,1024,256),(-16,0),(128,32)),((120,384,260,448),(22,0),(70,32))]:
 s=im.crop(rect).resize((round(geom[0]*.8*scale),round(geom[1]*.8*scale)),Image.Resampling.LANCZOS)
 canvas.alpha_composite(s,(round(100+pos[0]*scale),40))
# Runtime selects START for this prompt (the static placeholder is L2).
s=buttons.crop((320,0,384,64)).resize((102,102),Image.Resampling.LANCZOS);canvas.alpha_composite(s,(49,40));canvas.convert('RGB').save(O/'P2_JOIN_FIT.png')
print('Compact text ends at local 78; panel ends at 86.4. START icon preserved; text starts at 22.')
