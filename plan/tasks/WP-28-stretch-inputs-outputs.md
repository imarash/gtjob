# WP-28 (optional, wave 6): DOCX input, OCR fallback, LaTeX export

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 6 (optional; dispatch only after G5 approves) | Waves 1-5 | Sonnet (`cv-builder`) | M |

## Goal

Add three stretch capabilities, each behind a graceful dependency check:

- `.docx` CV input.
- An OCR fallback for scanned PDFs.
- A `--format latex` export of the render model, for users who want to hand-edit in Overleaf.

## Context

- Read `plan/tasks/_COMMON.md`.
- Skill dependency rule: the skill's PEP 723 dependency list is fixed (`jsonschema`, `pypdf`, `typst`). Each new
  capability uses an optional tool if present, and otherwise fails with exit 3 or 5 and an actionable hint:
  - DOCX: Python `docx2txt` if importable, else `pandoc` on PATH, else `textutil -convert txt` on macOS.
  - OCR: `ocrmypdf` or `tesseract` on PATH.
  - LaTeX: no dependency (string generation with escaping).
- WP-09 (`ingest.py`) owns extraction and already calls `cvtlib.extras.extract_docx` / `ocr_pdf` when the module
  exists. This WP provides that module. Do not edit `ingest.py`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/extras.py` (`extract_docx(path) -> str`, `ocr_pdf(path) -> str`)
- `.claude/skills/tailoring-cvs/scripts/cvtlib/latex.py` (`render_latex(model: dict) -> str` with full LaTeX
  escaping of `\ { } $ & # ^ _ % ~`)
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/export.py` (`cvt export RUN --format latex|md|jsonresume`)
- `tests/unit/test_extras.py`
- `plan/reports/WP-28.md`

## Steps

1. `extract_docx` with the fallback chain above and an exit-3 hint listing the options. `ocr_pdf` produces
   `cv.ocr.txt` and adds a source issue warning that OCR text needs checking.
2. `render_latex`: a single-file article class with a `\section*` per section. The escaping is exhaustive, and
   tests feed every special character through it.
3. Tests: a DOCX built in-test with `zipfile` (minimal `document.xml`) when no converter is present is expected to
   exit 3. LaTeX escaping covers every special character and an injection string (`\input{/etc/passwd}`) renders
   literally.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_extras.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-28.md` under `## ESCALATION`. Do not change it.
