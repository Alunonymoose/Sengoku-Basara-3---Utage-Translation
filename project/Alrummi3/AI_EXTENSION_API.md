# Alrummi 3 AI extension API

Alrummi 3 is designed to accept improvements from multiple local AIs without
locking the GUI to one model vendor.

## What an extension can provide

- OCR and Japanese text detection
- English translation suggestions
- Text-region detection
- Donor-texture matching
- Style/font recommendations
- Candidate renderers
- Archive/resource analyzers

The current stable contract is in `ai_extensions/api.py`:

```python
class AlrummiAIProvider(Protocol):
    provider_id: str
    display_name: str
    api_version: str

    def analyze_texture(self, image_png: bytes, texture_name: str) -> TextureAnalysis:
        ...
```

## Update rules

1. Put a new update in `updates/<name>/`.
2. Add a `manifest.json` with `id`, `name`, `version`, `api_version`, `capabilities`, and `description`.
3. Keep the provider offline.  Use a local endpoint or local model files only.
4. Return proposals; do not write ARC files from a provider.
5. Add fixtures or tests when changing decoding or rendering behavior.
6. Review and explicitly enable executable provider code before using it.

Alrummi 3 discovers manifests at startup, but it does not silently execute
new Python code.  That boundary is deliberate: different AIs can improve the
tool, while the user remains in control of code execution and archive writes.

