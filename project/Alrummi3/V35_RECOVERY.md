# Alrummi3 v35 recovery baseline

Canonical user-provided baseline from 2026-09-11: `dist-v35.zip` (`Alrummi3_2.0_studio.exe`) and `_bcn_validate.zip` (editable v35 source bundle).

Canonical GUI entrypoint is `alrummi3_v41.py`, layered on `alrummi3_v4.py`. The legacy `alrummi3_gui.py` executable is not the latest Alrummi build.

The uploaded source bundle omitted five runtime modules that were embedded in the v35 PyInstaller EXE. Their exact Python 3.11 bytecode was recovered from `PYZ.pyz` and committed as checksummed Base64 payloads so v35 remains reproducible without substituting older code.

Recovered modules: `drive_bridge`, `v4_mttex_codec`, `v4_image_edit`, `v41_image_edit`, `v41_donor_validate`.

`v41_selftest.py` was build-time only and was not bundled in the EXE. CI therefore performs checksum, import, syntax and full PyInstaller build checks directly instead of pretending to have recovered that source.
