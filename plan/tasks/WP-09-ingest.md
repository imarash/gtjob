# WP-09: Ingest (CV and JD text extraction and cleanup)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01 | Sonnet (`cv-builder`) | M |

## Goal

Turn the stored inputs into clean text: `cv.txt` and `jd.txt`. Strip extraction artifacts without
losing content or reading order. Detect scanned PDFs, and record method, pages, and warnings in
`state.ingest`.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 3 (`ingest` row), section 5 (WP-09 `ingest.py` block), section 6
  (`ingested` stage), and the `state.ingest` object in `state.schema.json`.
- Facts verified on the sample CV (`CVs/ArashMorattab-CV-2026-10.pdf`, a Google Docs export, 6 pages):
  - `pdftotext -layout` keeps the reading order and puts each employer's date range on the same line.
    Plain `pdftotext` (non-layout) splits them, so always use `-layout`.
  - Artifacts:
    - 189 U+200B zero-width spaces.
    - Decorative bullets ❖ (U+2756) and ➢ (U+27A2), and ♦ (U+2666) as a separator.
    - Right-aligned page numbers on their own line.
    - A repeated header on pages 2-6: `Arash Morattab ... me@arashmor.com ♦ www.ArashMor.com`.
    - A page-1-only header with the website and `♦ Updated: Oct 2025`.
  - The email appears only in the repeated headers. Keep one copy of the header text at the top of `cv.txt`, so
    the profile stage can still find the email. Strip the repeats.
  - The `pypdf` fallback (`extraction_mode="layout"`) works but emits ligatures (ﬁ) and odd spacing, so apply
    NFKC and collapse runs of spaces inside words cautiously.
- JD kinds: `file` and `text` are already stored in `inputs/jd.md` by `init`. For `url`, fetch with
  `urllib.request` (15 s timeout, User-Agent `gtjob/0.1`), strip HTML to text with the standard-library
  `html.parser`, dropping `script`, `style`, and `nav` content, and save the result to `inputs/jd.md`. If the
  network is unavailable, exit 5 with the hint "paste the JD text with --jd-text or save it to a file".

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/ingest.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/ingest.py`
- `tests/unit/test_ingest.py`
- `tests/fixtures/ingest/` (synthetic inputs you generate; see step 4)
- `plan/reports/WP-09.md`

## Steps

1. `extract_cv(path)`:
   - PDF: use `pdftotext -layout -enc UTF-8` if `shutil.which("pdftotext")`, else `pypdf` layout mode, else
     `CvtError(MISSING_DEPENDENCY)` with the hint "brew install poppler, or uv pip install pypdf".
   - Count pages with `pypdf`.
   - Scanned detection: fewer than `MIN_CHARS_PER_PAGE = 200` extractable characters per page on average sets
     `scanned_suspect`. Then exit 5 with the hint "this PDF looks scanned; export a text PDF or paste the CV as
     text (OCR is not supported yet)".
   - `.txt` and `.md`: read as UTF-8 (fall back to latin-1 with a warning).
   - Extension hook for optional extras: if `importlib.util.find_spec("cvtlib.extras")` is found, `.docx` calls
     `extras.extract_docx(path)`, and a scanned PDF calls `extras.ocr_pdf(path)` (with method `ocr`, a warning,
     and no exit 5). Without the module, `.docx` exits 5 with the hint "export the CV as PDF or text", and scanned
     PDFs exit 5 as above. Test both branches with a monkeypatched fake `cvtlib.extras`.
2. `clean_cv_text(raw)`:
   - Normalize (NFKC; remove U+200B, U+FEFF, and soft hyphens; non-breaking space → space).
   - Detect repeated header and footer lines: lines that, after normalization and digit-stripping, occur on
     ≥ 2 pages within the first or last `HEADER_SCAN_LINES = 4` non-empty lines of each page (split pages on
     form feed `\f`). Keep the first occurrence and remove the others.
   - Remove standalone page-number lines (`^\s*\d{1,2}\s*$`).
   - Replace decorative bullets (❖ ➢ • ▪ ◦ ● ■ ♦ and `DECORATIVE_GLYPHS` as a named constant) at the line start
     with `- `. A mid-line ♦ becomes ` | `.
   - Collapse runs of more than 2 spaces to 2. Keep the employer/date gaps, which helps the profile stage.
   - Collapse 3 or more blank lines to 1.
   - Return a list of warnings, for example "removed 5 repeated header lines", "stale 'Updated: Oct 2025' line kept
     for review".
3. `cvt ingest RUN`:
   - Writes `cv.txt` and `jd.txt` (JD via `load_jd` + `clean_jd_text`).
   - Records both artifacts and fills `state.ingest`.
   - Stage → `ingested`. Prints a summary: method, pages, chars, warnings.
4. Tests (no network):
   - Generate a synthetic 3-page PDF in the test with `typst.compile`. It should have a repeated header with an
     email, ❖ bullets, U+200B characters, page numbers, and an employer line with a right-aligned date. Assert
     that the cleaned text keeps one header, has no glyphs or page numbers, and keeps the bullet order.
   - Run the `.txt` path on `tests/fixtures/cv/jamie-rivera-junior.txt` (from WP-04; skip if it is absent).
   - The scanned path: a PDF with an image only, or with no text. Expect exit 5.
   - Monkeypatch the pdftotext-missing path to cover the `pypdf` fallback.
   - The URL path: use a local `http.server` on 127.0.0.1 serving an HTML JD, and check the stripped text.
   - `@pytest.mark.sample` test: ingest the real sample CV. Assert 6 pages, the email present exactly once, no
     U+200B or ❖ characters, "Role: SRE" present twice, and "Feb 2024 - Present" on the same line as
     "Altimetrik".

## Token-efficiency requirements (interfaces.md section 14)

- Line stability: profile maps cite `cv.txt` line numbers, so `cv.txt` must be deterministic for the same input
  bytes. For `.txt` and `.md` inputs without form feeds, repeated headers, or decorative glyphs, `clean_cv_text`
  keeps the line count and order unchanged (in-line normalization only). Test this on the junior CV fixture: line
  count and order are unchanged, and the content matches after NFKC.
- `ingest` prints at most 4 lines: method, pages, characters, and warnings count. Its `--json` data has no text
  bodies.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_ingest.py              # passes (sample test may skip)
uv run pytest -q tests/unit/test_ingest.py -m sample    # passes on the planner's machine (sample present)
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-09.md` under `## ESCALATION`. Do not change it.
