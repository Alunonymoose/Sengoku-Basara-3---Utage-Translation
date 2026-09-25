from scra_validate import path_hash, parse_scra
import struct

def test_path_hash_vectors():
    assert path_hash(r"id\texture\jpn\charasele_01\charasele_01_000_ID_HQ") == 0x34E2C6CE
    assert path_hash(r"id\texture\jpn\charasele_02\charasele_02_000_ID_HQ") == 0xF51E09E7
    assert path_hash(r"id\texture\jpn\kamon\kamon_000_ID_HQ") == 0x4799A0EA
    assert path_hash(r"id\texture\jpn\army\army_000_ID_HQ") == 0xE755AC4C

def test_scra_parse():
    pairs=[(0x241F5DEB,0x34E2C6CE),(0x241F5DEB,0xF51E09E7)]
    blob=b"SCRA"+struct.pack(">HH",8,len(pairs))+b"".join(struct.pack(">II",*p) for p in pairs)
    assert parse_scra(blob)==(8,pairs)
