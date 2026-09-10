from __future__ import annotations

import zipfile

import package_v6


if __name__ == "__main__":
    with zipfile.ZipFile(package_v6.BASE_ZIP) as archive:
        base_tenka = archive.read(package_v6.TARGET_REL.as_posix())
    (package_v6.ROOT / "_v5_tenka_id_for_manifest.arc").write_bytes(base_tenka)
    package_v6.main()
