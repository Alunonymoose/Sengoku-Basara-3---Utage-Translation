meta:
  id: mt_framework_ps3_xet
  title: MT Framework PS3 XET header/mip-table structural fixture
  endian: be
  license: CC0-1.0
doc: |
  Independent read-only structural description derived from the recovered Foundry XET contract.
  It describes the 20-byte minimum header and variable mip offset table only.
  BC payload/channel interpretation and production writing remain in the verified Foundry codec.
seq:
  - id: magic
    contents: [0x00, 0x58, 0x45, 0x54]
  - id: version_flags
    type: u4
  - id: tex_flags
    type: u4
  - id: flags
    type: u4
  - id: mip_offsets
    type: u4
    repeat: expr
    repeat-expr: mip_count
instances:
  mip_count:
    value: tex_flags & 0x3f
  width:
    value: (tex_flags >> 6) & 0x1fff
  height:
    value: (tex_flags >> 19) & 0x1fff
  format_id:
    pos: 14
    type: u1
