# v0.1 public patch package

This directory defines the intended structure of the first public patch package.

The repository does **not** contain retail Utage files. Before publishing v0.1, generate binary deltas from a verified clean BLJM60389 base to the approved v0.1 localisation build.

Expected release archive:

```text
Sengoku_BASARA_3_Utage_English_v0.1/
├── apply_patch.ps1
├── manifest.json
├── README.txt
├── patches/
│   ├── ...
└── tools/
    └── xdelta3.exe   (optional; may instead require xdelta3 on PATH)
```

## Release-production checklist

1. Freeze the exact approved v0.1 live build.
2. Identify every game file whose bytes differ from the supported clean BLJM60389 base.
3. Record SHA-256 for every clean source and every v0.1 result.
4. Generate one delta for each changed retail-derived file.
5. Populate `manifest.json`.
6. Test installation against a completely clean extracted game copy.
7. Verify the patched tree matches the frozen v0.1 build byte-for-byte for every manifest target.
8. Boot-test the resulting build on RPCS3.
9. Where available, test the same file-level patch on real PS3 hardware.
10. Publish only the installer, manifests, project-created material and binary delta patches — not complete retail game files.

Until steps 1–9 are complete, a GitHub tag named v0.1 should be considered a development milestone rather than an installable public release.
