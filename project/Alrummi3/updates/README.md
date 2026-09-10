# Alrummi 3 update drop-zone

This folder is intentionally open for future updates from other local AIs or
contributors.

An update may add a subfolder containing:

```text
updates/<update-name>/manifest.json
updates/<update-name>/README.md
updates/<update-name>/provider.py       optional, reviewed manually
updates/<update-name>/tests/             optional fixtures
```

The manifest is discovered and shown by Alrummi 3.  Python files are not
executed automatically.  This keeps a downloaded or AI-generated update from
gaining archive-write access without review.

Providers should target the contract in `ai_extensions/api.py` and return
analysis or generation proposals.  They must not overwrite the source ARC.
The GUI's confirmation action is the only path that writes a replacement ARC.

