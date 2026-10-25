# WP-14: Page fit, ATS round-trip, keyword coverage, `validate`

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-12 (render), WP-13 (provenance) | Sonnet (`cv-builder`) | L |

## Goal

Fit the CV to exactly the page target with a monotone, non-oscillating search, then run every hard gate on the
rendered PDF and write `validation.json`. Copy the final PDF to `final/` only when everything passes.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 9 (the fit algorithm is normative), section 10 (gates table is normative),
  section 3 (`fit` and `validate` rows), section 5 (WP-14 block, implemented here), `fit.schema.json`, and
  `validation.schema.json`.
- APIs you call:
  - `cvtlib.render.render_run(run_dir, density=..., dropped_ids=..., draft=..., png=..., out_pdf=...)` → `RenderResult`
    (WP-12).
  - `cvtlib.provenance.check_tailored`, `check_logistics`, and `find_placeholders` (WP-13).
  - `cvtlib.profile.merged_view` (WP-10) and `cvtlib.attestations.usable` (WP-11).
- Use a scratch output path (`build/fit-try.pdf`) for search compiles, so `cv.pdf` only ever holds the final fit.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/fit.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/ats.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/coverage.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/validate.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/fit.py` (`fit`, `validate`)
- `tests/unit/test_fit.py`, `tests/unit/test_validate.py`
- `plan/reports/WP-14.md`

## Steps

1. `drop_order(tailored)`, exactly per section 9. Effective priority = `max(bullet.priority, parent.priority)`.
   Ordering: priority descending, then employer age (oldest `start_date` first), then position (last first).
   Exclude priority 1.
2. `fit_run(run_dir, png)`:
   - Run the density pass, then a binary search on `k` with `compact`.
   - Write the `log` lines (for example `"standard: 3 pages"`, `"k=12: 2 pages"`), `renders`, and `underfilled`.
   - Write `fit.json` and do the final render (PNGs only when `--png` is given).
   - Exit 1 with the section 9 message when priority-1 content overflows.
   - `MAX_RENDERS = 24` as a named safety cap. Exceeding it is exit 7.
3. `ats.extract_pdf_text`: `pdftotext -layout`, else `pypdf`. Apply NFKC.
4. `ats.ats_check(pdf_text, model, jd)` implements the `ats_roundtrip` row checks. Each failure is a violation with
   code `ats_missing`, `ats_order`, or `ats_garbage`, and a precise message. Order checking finds the first
   occurrence index of each section title and employer heading in extraction order.
5. `coverage.coverage(pdf_text, jd)`: for each must requirement's keywords and keyword synonyms, case-insensitive
   with word boundaries. Fill `by_requirement` for all requirements; `missing` lists must keywords that were not
   found.
6. `validate.validate_run(run_dir, draft)`:
   - Run every gate in the section 10 order and write `validation.json`.
   - The `typography_floor` gate reads `presets.json` and checks that the `build/render.json` density preset values
     are ≥ `floor`.
   - The `page_count` gate reads `fit.json` and the PDF page count. They must agree.
   - On pass without draft, copy to `final/<Name>-<TitleSlug>[-<CompanySlug>].pdf` and record `final_pdf`. Stage →
     `validated`.
   - Print a compact gate table and the coverage percentage.
7. Commands `fit RUN [--png]` and `validate RUN [--draft]`. `fit` requires stage ≥ `approved`, or the `--draft`
   option on the run; `validate` requires `rendered`.
8. Tests:
   - `drop_order` on the junior golden and a synthetic many-bullet tailored file.
   - Monotonicity: page count is non-increasing as `k` grows. Check this on a synthetic tailored file built in the
     test (40 bullets), and assert that fit picks the minimal `k`.
   - Pinned overflow → exit 1.
   - The underfilled flag (junior, `page_target` 2 → underfilled; `page_target` 1 → pass).
   - ATS: a missing email, sections out of order (build a render model with swapped sections), `(cid:` garbage
     (synthetic text).
   - Coverage counts.
   - Placeholders: `validate` without draft fails, with draft warns.
   - A full `validate` on the junior golden run, built with `init` → copy goldens → `check-tailored` → `approve
     --all` (if WP-16 is present; otherwise set the stage directly through `cvtlib.state` in the test) → `fit` →
     `validate`, which passes and writes `final/`.

## Token-efficiency requirements (interfaces.md section 14)

- `fit` renders PNGs only with `--png`. The default path is PDF only.
- Add the `layout` gate to `validate` (warn only, section 14.5):
  - The last-page fill ratio comes from the y of the last text line (pypdf, or `pdftotext -bbox` when available)
    over the usable page height. Warn below `MIN_LAST_PAGE_FILL = 0.25`.
  - `underfilled` comes from `fit.json`.
  - Orphan heading: a section title among the last `ORPHAN_HEADING_LINES = 2` text lines of a page (only with
    bbox data).
  - Each warning names the page number, so the agent can view only that page.
- `validate` prints at most 10 lines: one line per non-pass gate, the final PDF path, and `next_action`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_fit.py tests/unit/test_validate.py   # passes
```

## Definition of done

The common definition of done. The report includes the fit log for the junior run and the synthetic 40-bullet run.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-14.md` under `## ESCALATION`. Do not change it.
