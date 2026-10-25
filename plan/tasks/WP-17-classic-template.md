# WP-17: `classic` template (and optional `sidebar` variant)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-02 (fonts, fixtures), WP-12 (`common.typ`, render pipeline) | Sonnet (`cv-builder`) | M |

## Goal

Add a second template on the same data contract. It should have the look of the best LaTeX CVs
(Jake's Resume's clean serif hierarchy and Awesome-CV's section treatment): ATS-safe, single column,
Libertinus Serif.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: `render-model.schema.json` and interfaces.md section 9. The template must read only `render.json` and
  `presets.json`, must use `common.typ` helpers where they fit, and must never `eval`.
- `cvtlib.render.write_build` (WP-12) copies `<template>.typ` + `common.typ` + `presets.json` into `build/`.
  Adding a template means adding the `.typ` file. If WP-12 hard-coded a template list, do not edit `render.py`.
  Report it under ESCALATION, and the integration WP fixes it.

## Owned files

- `.claude/skills/tailoring-cvs/assets/templates/classic.typ`
- `.claude/skills/tailoring-cvs/assets/templates/sidebar.typ` (optional; header comment "less ATS-safe")
- `tests/unit/test_template_classic.py`
- `plan/reports/WP-17.md`

## Steps

1. `classic.typ`:
   - Centered name in small caps, then the headline, then one contact line with links.
   - Section titles in small caps with a full-width thin rule beneath (Jake's style).
   - Entry heads: employer in bold on the left with dates on the right; title in italic with location on the right.
   - Client subentries are indented, with "Client — Role" in italic.
   - Bullets are tight. Body size and margins come from the density preset.
   - Black text only, or a very dark accent for rules.
   - Same metadata, draft highlight, and footer behavior as `modern` (reuse `common.typ`).
2. `sidebar.typ` (optional, only if time permits): a two-column layout with skills and certifications in a narrow
   left column. Add the header comment `// Less ATS-safe: column layout may confuse some parsers.` If you skip it,
   say so in the report.
3. Tests:
   - Compile both `tests/fixtures/render/*.json` with `classic` through `cvtlib.render.compile_pdf` / `write_build`.
     The junior fixture fits 1 page; the senior fixture at `compact` fits ≤ 3 pages.
   - Fonts embedded are Libertinus.
   - pdftotext (when available) keeps the sections in order and the employer and dates on one line.
   - Markup-like strings render literally.
   - Write PNGs to `.cache/test-artifacts/render/classic-*.png` for the gate reviewer.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_template_classic.py   # passes
ls .cache/test-artifacts/render/classic-*.png           # at least 2 files
```

## Definition of done

The common definition of done. The report embeds or links page-1 PNGs of both fixtures.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-17.md` under `## ESCALATION`. Do not change it.
