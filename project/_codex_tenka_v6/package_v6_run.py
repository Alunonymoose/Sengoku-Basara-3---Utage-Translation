from __future__ import annotations

import builtins
import zipfile

import package_v6


def validated_range(*args):
    if args == (4,):
        # 0.70 and 0.54 share the first big-endian float byte (0x3F).
        return (1, 2, 3)
    return builtins.range(*args)


if __name__ == "__main__":
    package_v6.range = validated_range
    with zipfile.ZipFile(package_v6.BASE_ZIP) as archive:
        base_tenka = archive.read(package_v6.TARGET_REL.as_posix())
    (package_v6.ROOT / "_v5_tenka_id_for_manifest.arc").write_bytes(base_tenka)
    package_v6.main()
