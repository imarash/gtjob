# WP-FIX-2-2: Move the sample candidate's personal data out of committed tests

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2) | WP-09, WP-12, WP-I2 | Sonnet (`cv-builder`) | S |

## Goal

`_COMMON.md` section 4: never copy personal data into committed files. Three wave 2 test files assert literal values
taken from the real sample CV (`CVs/…pdf`, git-ignored):

- `tests/unit/test_ingest.py`, `test_real_sample_cv` (around lines 302-318): the candidate's email address, and the
  name of their current employer used to find the employer/date line.
- `tests/integration/test_wave2.py`, `SAMPLE_REQUIRED_TEXT` (line 32): three real employer/client/university names
  from the sample, used by `test_sample_cv_ingest`.
- `tests/unit/test_render.py` (around lines 150-162): an earlier-experience item whose employer, title, and dates are
  copied from the sample CV.

Keep every check, but read the literal values from a git-ignored private file, or replace them with structural checks.
The sample tests must still run (not skip) on a machine that has the sample CV and the private file.

## Context

- Read `plan/tasks/_COMMON.md`.
- `tests/fixtures/private/` is git-ignored (`.gitignore` line 7). WP-20 owns `tests/fixtures/private/sample/`, so do
  **not** write inside `sample/`. Use the file `tests/fixtures/private/sample-ingest.json`.
- `tests/conftest.py` provides `sample_cv_path` (skips when the CV is absent). Do not edit `conftest.py`.
- Get the real values by running the existing tests' logic on the sample, never by typing them into a tracked file.

## Owned files

- `tests/unit/test_ingest.py` (the `sample` test only)
- `tests/integration/test_wave2.py` (`SAMPLE_REQUIRED_TEXT` and `test_sample_cv_ingest` only)
- `tests/unit/test_render.py` (the earlier-experience test data only)
- `tests/fixtures/private/sample-ingest.json` (new, git-ignored, never committed)
- `plan/reports/WP-FIX-2-2.md`

## Steps

1. Create `tests/fixtures/private/sample-ingest.json`:
   `{"email": "...", "current_employer": "...", "required_text": ["...", "...", "..."], "pii_literals": [...]}`.
   Fill `email`, `current_employer`, and `required_text` with the exact values the tests use today. Set `pii_literals`
   to the union of all of them, plus the candidate's surname and email domain as they appear in the CV.
2. `test_ingest.py`: in `test_real_sample_cv`, load that file (`pytest.skip` with a clear reason when it is absent) and
   use its `email` and `current_employer` instead of the literals. Keep all other assertions.
3. `test_wave2.py`: delete `SAMPLE_REQUIRED_TEXT`; `test_sample_cv_ingest` loads `required_text` from the same file
   (skip when absent). Keep the page-number, header-dedup, and glyph assertions. Put the file path in a module-level
   constant.
4. `test_render.py`: replace the copied employer/title/dates with invented ones (for example `Pinecrest Hosting`,
   `Systems Administrator`, `2010-03` to `2010-11`), and update the expected line to match.
5. Report: list what changed per file. **Do not paste any value from the private file into the report.**

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_ingest.py tests/unit/test_render.py tests/integration/test_wave2.py   # passes
uv run pytest -q tests/unit/test_ingest.py -m sample                       # 1 passed (not skipped) on this machine
git check-ignore -q tests/fixtures/private/sample-ingest.json && echo "private file ignored"
python3 -c 'import json;print("\n".join(json.load(open("tests/fixtures/private/sample-ingest.json"))["pii_literals"]))' > .cache/pii.txt \
  && git grep --untracked -n -i -F -f .cache/pii.txt -- tests/unit/test_ingest.py tests/integration/test_wave2.py tests/unit/test_render.py; \
  test $? -eq 1 && echo "no sample PII in owned files"
uv run pytest -q tests/unit tests/integration                               # passes
# informational only (not pass/fail): other tracked files with hits, reported as file:count
git grep --untracked -c -i -F -f .cache/pii.txt -- tests .claude src
```

For the informational grep, list each file and count under `## Open issues` in your report (never the matched value),
and do not edit those files. Known wave 1 hits are expected (`tests/conftest.py` sample path, the PII-marker lists in
`tests/unit/test_refs_*.py`, and possibly `references/answer-parsing.md`).
