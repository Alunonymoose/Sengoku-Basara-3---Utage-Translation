from __future__ import annotations

import base64
import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMPORT = ROOT / "_v35_import"
MANIFEST = IMPORT / "manifest.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    encoded = bytearray()
    for item in manifest["parts"]:
        path = IMPORT / item["name"]
        raw = path.read_bytes()
        actual = sha256(raw)
        if actual != item["sha256"]:
            raise SystemExit(f"checksum mismatch for {path.name}: {actual}")
        encoded.extend(raw.strip())

    archive = base64.b64decode(bytes(encoded), validate=True)
    actual_archive = sha256(archive)
    if actual_archive != manifest["archive_sha256"]:
        raise SystemExit(f"archive checksum mismatch: {actual_archive}")

    archive_path = IMPORT / manifest["archive_name"]
    archive_path.write_bytes(archive)

    with tarfile.open(archive_path, "r:xz") as tf:
        root = ROOT.resolve()
        for member in tf.getmembers():
            target = (ROOT / member.name).resolve()
            if target != root and root not in target.parents:
                raise SystemExit(f"unsafe archive member: {member.name}")
        tf.extractall(ROOT)

    print(f"restored Alrummi3 v35 delta: {actual_archive}")


if __name__ == "__main__":
    main()
