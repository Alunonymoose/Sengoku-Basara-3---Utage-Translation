from mt_hash import mt_hash_v2


def test_known_sb3_resource_class_hashes():
    assert mt_hash_v2("rTexture") == 0x241F5DEB
    assert mt_hash_v2("rMessage") == 0x10C460E6
    assert mt_hash_v2("rLayoutSpr") == 0x60DD1B16
    assert mt_hash_v2("rArchive") == 0x73850D05
