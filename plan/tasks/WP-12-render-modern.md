# WP-12: Render pipeline and `modern` template

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01, WP-02 (fonts, presets, render fixtures), WP-04 (junior tailored) | Sonnet (`cv-builder`) | L |

## Goal

Implement `tailored.json` → render model → Typst source → PDF/PNG/Markdown, with the default `modern`
template. Output is polished, ATS-safe, single-column, and two pages. It should be at least as good as
the candidate's current CV and Awesome-CV/Jake's Resume.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: `render-model.schema.json` (template data contract), `tailored.schema.json`, `fit.schema.json`,
  interfaces.md section 3 (`render` row), section 5 (WP-12 `render.py` block, implemented here), and section 9
  (mapping rules, compilation, backends, presets).
- Verified: the PyPI `typst` 0.15 wheel works in the Cursor sandbox. Its signature is
  `typst.compile(input, output=None, root=None, font_paths=..., ignore_system_fonts=False, format=None, ppi=None, sys_inputs=..., pdf_standards=..., ...)`.
  It sets PDF title/author from `set document(...)`. `format="png"` with multiple pages: check the return type
  (list of bytes or an output pattern such as `page-{p}.png`) and handle both. Typst 0.14+ emits tagged PDFs by
  default; verify with `pdfinfo` ("Tagged: yes") where Poppler exists.
- Fonts: `assets/fonts/source-sans-3/` (modern). Check the exact family name in `assets/fonts/FONTS.md` (WP-02).
- Security: templates read data with `json()` and insert strings as content. Never use `eval`, and never build Typst
  markup by string concatenation in Python, except for the fixed template copy.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/render.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/render.py`
- `.claude/skills/tailoring-cvs/assets/templates/common.typ`
- `.claude/skills/tailoring-cvs/assets/templates/modern.typ`
- `tests/unit/test_render.py`
- `plan/reports/WP-12.md`

## Steps

1. `build_render_model(tailored, dropped_ids, density, draft, paper, template)`. Pure function, per section 9:
   - Header contacts in order: email (`mailto:`), phone (`tel:`), location, website/links. Labels show the
     bare domain or handle.
   - Sections in order:
     - `summary`.
     - `skills`, with the label and comma-joined items.
     - `experience`. Drop `dropped_ids` bullets. Engagements with no bullets fold into `collapsed_line`, formatted
       as `"Also: <name> (<role_label>) · ..."`.
     - `earlier`, when `include` and non-empty, with lines like `"Mindgeek — Devops Engineer (2017)"`.
     - `certifications`, minus dropped IDs.
     - `education`.
   - Date formatting: `2024-02` → `Feb 2024`, `present` → `Present`, year-only stays as is, and ranges use an
     en dash with spaces.
   - Meta: title `"<name> — CV — <target.title>"`, author = name, subject = target title, keywords = the top 12
     JD terms present in skills (taken from tailored skills, in order). Draft flag.
   - Accent `#1F4E79` by default as the named constant `DEFAULT_ACCENT`. The template may override per theme.
2. `common.typ` helpers:
   - `section-title(title, accent)` with a subtle rule.
   - `entry-head(heading, subheading, location, dates)`: the employer on the left in bold, the dates
     right-aligned on the same line. Use a grid; ATS extraction keeps it on one line.
   - `bullets(list)` with a tight hanging indent.
   - `contact-line(contacts)` with real links and a separator that ATS reads as text (`·` or `|`).
   - A placeholder highlight: `show regex("\[\[CONFIRM:[^\]]*\]\]")` sets red text when `draft`.
   - A draft footer "DRAFT: unconfirmed items".
3. `modern.typ`:
   - Single column. The name is large and semibold, with the accent color on the name or the section rules only
     (restrained).
   - The headline sits under the name, then the contact line.
   - Sizes come from the density preset (`presets.json`).
   - Section titles are small caps or tracked uppercase.
   - Client subentries are indented, with a subheading for the role label.
   - Page numbers show as "2 / 2" in the footer, in text and not decorative.
   - No icons, tables, or columns that break the ATS reading order.
   - Set the PDF language to English and the document title, author, and keywords.
4. `write_build`, `compile_pdf`, `compile_png`, and `render_markdown` per the contract.
   - Backend detection order: python `typst` → `typst` binary → none, which writes `build/` and `cv.md` and raises
     `MISSING_DEPENDENCY`.
   - `render_markdown` produces a clean Markdown CV (always written as `cv.md`).
5. `render_run(...)` and `cvt render RUN [--template] [--density] [--draft] [--png] [--ppi] [--pages N[,N]]`:
   - `--pages` is view-only. It rasterizes the listed pages of the existing `cv.pdf` into `pages/page-<N>.png`, using
     `pdftoppm -f N -l N -r PPI -png` when present, else Typst PNG output from `build/cv.typ` keeping only those
     pages. It never rebuilds, never changes the stage, and never marks artifacts stale. With no `cv.pdf`, exit 4
     with a hint to run `fit`. Test that a validated run stays `validated` after `render --pages 1`.
   - Use `fit.json` when its `tailored_version` matches, and otherwise render without drops (warn "not fitted;
     run cvt fit").
   - If the stage is before `approved`, force `draft`.
   - Record the `render_model`, `typst_source`, `pdf`, `pages_png`, and `markdown_fallback` artifacts. Stage →
     `rendered` only when the stage is ≥ `approved`.
   - Print the page count and paths.
   - `--template classic` must work once WP-17 lands. Until then, exit 2 with "template not installed".
6. Tests:
   - The render model built from the junior golden tailored file validates against the schema.
   - Dropping IDs folds engagements into `collapsed_line`.
   - Date formatting.
   - Compile `tests/fixtures/render/junior-render.json` → 1 page, and `senior-render.json` at `compact` → ≤ 3
     pages.
   - `pypdf` metadata title and author are set, and the fonts are embedded.
   - pdftotext extraction (when available) keeps the "Employer ... Feb 2024 – Present" on one line, and the
     sections in order.
   - PNG export count equals the page count.
   - The missing-backend path writes `cv.md` and exits 3.
   - A JSON string containing Typst markup (for example `#eval("1")` and `*bold*`) renders literally.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_render.py   # passes
# visual artifact for the gate reviewer:
uv run python - <<'EOF'
import sys; sys.path.insert(0, ".claude/skills/tailoring-cvs/scripts")
from pathlib import Path
from cvtlib import render
print(render.__name__, "ok")
EOF
```

The reviewer also opens the PNGs that the test writes to `.cache/test-artifacts/render/`. The test must write them there.

## Definition of done

The common definition of done, plus a screenshot-quality PNG of the senior fixture at standard density, saved to
`.cache/test-artifacts/render/senior-standard-page-1.png` and mentioned in the report.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-12.md` under `## ESCALATION`. Do not change it.
