from common import *
root=Path(r'E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng')
for p in [*root.glob('*.arc'),*(root/'tenka').glob('*.arc')]:
 a=arc.parse_arc(p)
 for e in a.entries:
  if e.name.endswith('charasele_00_000_ID_HQ'):
   r=arc.unpack(e);(W/'sh_charasele.tex').write_bytes(r);preview(unpack_color(decode(r)),W/'sh_charasele.png');print(p,e.index,xet_info(r));raise SystemExit
