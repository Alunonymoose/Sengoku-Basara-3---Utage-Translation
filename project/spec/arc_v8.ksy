meta:
  id: mt_framework_lite_arc_v8_ps3
  title: MT Framework Lite ARC v8 (PS3 structural fixture)
  endian: be
  license: CC0-1.0
doc: |
  Independent structural description of the ARC v8 container used by Sengoku BASARA 3 Utage.
  Production writes remain owned by the verified safe_arc/Foundry writers.
  Compression semantics are intentionally not guessed here; stored payload bytes are exposed verbatim.
seq:
  - id: magic
    contents: [0x00, 0x43, 0x52, 0x41]
  - id: version
    type: u2
    valid: 8
  - id: entry_count
    type: u2
  - id: entries
    type: entry
    repeat: expr
    repeat-expr: entry_count
types:
  entry:
    seq:
      - id: name_raw
        size: 64
      - id: type_hash
        type: u4
      - id: stored_size
        type: u4
      - id: packed_size
        type: u4
      - id: payload_offset
        type: u4
    instances:
      declared_raw_size:
        value: packed_size >> 3
      flags:
        value: packed_size & 7
      stored_payload:
        io: _root._io
        pos: payload_offset
        size: stored_size
