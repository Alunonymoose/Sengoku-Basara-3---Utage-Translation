# Alrummi3 v35 verified source recovery

This directory stores the checksum-verified transport used to recover the current Alrummi3 v35/v4.1 source delta from the user's authoritative 2026-09-11 v35 source/binary uploads.

- Runtime entrypoint: `alrummi3_v41.py`
- Main implementation: `alrummi3_v4.py`
- Python: 3.11
- Restored delta SHA-256: `00c7e8a32966a6d4c4759ca739063d3f726bd4d0f524b7217bf28dfaaac14592`
- Attachment-aware verified build commit: `9d284f0d40c20ded99c86cede236b90ed0ccb79f`
- Verified CI run: `34650426733`
- Verified EXE SHA-256: `5B8DC3D1954A6543E04FA2E8F98AD485B9E24D4508DFE2133A4E02C49C62ABC8`

`restore_v35_delta.py` verifies every transport part plus the final archive before extraction. `apply_v35_attachment_handoff.py` integrates the real Selenium PNG attachment flow into v35 while retaining the original clipboard/Explorer fallback and never submitting the ChatGPT prompt automatically.

The old `alrummi3_gui.py` remains a historical module/dependency. It is not the current Windows application entrypoint and must not be used as the top-level build target.
