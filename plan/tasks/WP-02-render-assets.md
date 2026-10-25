# WP-02: Render assets (OFL fonts, presets, render fixtures)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 | Wave 0 contracts | Haiku (`cv-builder-lite`; re-dispatch to `cv-builder` on PARTIAL) | S |

## Goal

Bundle reproducible, OFL-licensed fonts for the two templates. Create `presets.json`, the
density/typography table that templates and validators share. Write two synthetic render-model
fixtures that WP-12 and WP-17 use to develop templates without the rest of the pipeline.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: `plan/contracts/render-model.schema.json`, and interfaces.md section 9 (presets values and compilation).
- Typst compiles with `ignore_system_fonts=True` and `font_paths=[assets/fonts]`. Only fonts in `assets/fonts/` exist for it.
- Fonts chosen in the plan:
  - `modern`: **Source Sans 3** (Adobe, OFL-1.1), release `3.052R` at
    https://github.com/adobe-fonts/source-sans/releases/tag/3.052R.
  - `classic`: **Libertinus Serif** (OFL-1.1), release `v7.051` at
    https://github.com/alerque/libertinus/releases/tag/v7.051.
- Network: GitHub release downloads are allowed in the sandbox. Use `curl -L`.

## Owned files

- `.claude/skills/tailoring-cvs/assets/fonts/source-sans-3/` (`SourceSans3-Regular.otf`, `-It.otf`, `-Semibold.otf`, `-Bold.otf`, `OFL.txt`)
- `.claude/skills/tailoring-cvs/assets/fonts/libertinus/` (`LibertinusSerif-Regular.otf`, `-Italic.otf`, `-Semibold.otf`, `-Bold.otf`, `OFL.txt`)
- `.claude/skills/tailoring-cvs/assets/fonts/FONTS.md`
- `.claude/skills/tailoring-cvs/assets/templates/presets.json`
- `tests/fixtures/render/senior-render.json`, `tests/fixtures/render/junior-render.json`
- `tests/unit/test_render_assets.py`
- `plan/reports/WP-02.md`

## Do not touch

The Typst templates (WP-12, WP-17), everything else under `assets/`, and `plan/contracts/*`.

## Steps

1. Download the release archives. Use the GitHub API (`https://api.github.com/repos/<owner>/<repo>/releases/tags/<tag>`)
   to find the asset names, then extract only the four static OTF weights listed above and each
   project's `OFL.txt` or `LICENSE.md`. Save the license verbatim as `OFL.txt`. If a weight file name differs, keep
   the upstream name and note it in `FONTS.md`. If Libertinus has no Semibold, keep Regular, Italic,
   and Bold, and note it.
2. `FONTS.md`: for each family, list the name, version, source URL, license (OFL-1.1), the file list with
   SHA-256 sums, and the Typst family name (check it with
   `uv run --with typst python -c "import typst; ..."` or `typst fonts --font-path ... --ignore-system-fonts`).
3. `presets.json`: exactly the JSON block in interfaces.md section 9 (`floor`, `comfortable`, `standard`, `compact`).
4. `senior-render.json`: a synthetic person ("Alex Chen", invented employers, no real PII) that validates against
   `render-model.schema.json`. Give it 4 employers, one with 3 client subentries, an earlier line, 8
   certifications, and education. Size it to about 2.3 pages at `standard` density, so fit has work to do.
   Include one `[[CONFIRM: number of services]]` placeholder in a bullet and set `meta.draft: true`.
5. `junior-render.json`: a synthetic junior ("Jamie Rivera") with 2 roles and 1 page of content, `draft: false`.
6. `test_render_assets.py`:
   - Both fixtures validate against the schema.
   - `presets.json` matches the section 9 values, and the `compact` values equal `floor`.
   - A tiny Typst document using each family compiles with
     `typst.compile(..., font_paths=[fonts], ignore_system_fonts=True)` and produces a PDF whose font list
     (read with `pypdf`) contains the family.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_render_assets.py        # passes
ls .claude/skills/tailoring-cvs/assets/fonts/*/OFL.txt   # two files
du -sh .claude/skills/tailoring-cvs/assets/fonts         # < 6 MB
```

## Definition of done

The common definition of done, plus: `FONTS.md` lists checksums matching the files.

## Escalation

If a release or font file is unavailable, do not substitute a non-OFL font. Use another OFL family with a
similar role (Source Serif 4 for classic, IBM Plex Sans for modern), record why under `## ESCALATION`, and
continue.
