# Bundled fonts

Typst compiles with `ignore_system_fonts=True` and `font_paths=[assets/fonts]`, so only these fonts exist for the
templates. Both families are licensed under the SIL Open Font License 1.1; each license is saved verbatim as
`OFL.txt` next to its fonts. Total size is about 2.4 MB.

## Source Sans 3 (template `modern`)

- Version: 3.052R (Adobe)
- Source: https://github.com/adobe-fonts/source-sans/releases/tag/3.052R
- License: OFL-1.1 (`source-sans-3/OFL.txt`)
- Typst family name: `Source Sans 3`. The Semibold weight registers as a separate family, `Source Sans 3 Semibold`.

| File | SHA-256 |
| --- | --- |
| `source-sans-3/SourceSans3-Regular.otf` | `08df266400933d3178d081a45f94a08814c3e55b4b7dd2e0ff69cb1329f13ab6` |
| `source-sans-3/SourceSans3-It.otf` | `430b9f0eb1170be0981706d14b6cf87122efba9d86c373bbdf69daf276421462` |
| `source-sans-3/SourceSans3-Semibold.otf` | `36f1cd2c344aa3109e64429bce41a41e4b2b923beb2db19b8dbf9bb56f05a4f9` |
| `source-sans-3/SourceSans3-Bold.otf` | `7776ddb9f3eb58683e59f28d558d8896b768c2d0c80799fb3f1c56c54dfd98c9` |

The upstream name for the italic is `-It.otf` (kept as is).

## Libertinus Serif (template `classic`)

- Version: v7.051 (Libertinus Project)
- Source: https://github.com/alerque/libertinus/releases/tag/v7.051
- License: OFL-1.1 (`libertinus/OFL.txt`)
- Typst family name: `Libertinus Serif`. The Semibold weight registers as a separate family,
  `Libertinus Serif Semibold`.

| File | SHA-256 |
| --- | --- |
| `libertinus/LibertinusSerif-Regular.otf` | `fcf06307a77367394fcb0ccb241e59eea70dba3d732be309647611224679c733` |
| `libertinus/LibertinusSerif-Italic.otf` | `9a393d63d6e05f620d3dc0190dfd35a8ede58c0808cf0fc9de7fcb9c723e4c24` |
| `libertinus/LibertinusSerif-Semibold.otf` | `a4b3f28e85881db34695c1f005e4c79233a6caf3a2bd286c9b418c025fb99308` |
| `libertinus/LibertinusSerif-Bold.otf` | `0264914210ed51b3231ebc92ce529e9f2e166ba9eebf0cd4a579558690a27b64` |

## Verify

```bash
typst fonts --font-path .claude/skills/tailoring-cvs/assets/fonts --ignore-system-fonts
shasum -a 256 .claude/skills/tailoring-cvs/assets/fonts/*/*.otf
```

`tests/unit/test_render_assets.py` checks that the checksums above match the files.
