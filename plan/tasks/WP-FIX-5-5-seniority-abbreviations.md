# WP-FIX-5-5: abbreviated seniority words ("Sr.", "Snr", "Jr.") are checked like the full words

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5 re-gate 1) | WP-FIX-5-4 | Haiku (`cv-builder-lite`) | XS |

## Goal

WP-FIX-5-4 added `provenance.SENIORITY_WORDS`, so the headline "Senior DevOps Engineer" on the junior golden is now
reported. The usual title abbreviations still get through. Each of these gave **no** violation from
`provenance.check_tailored` on `tests/fixtures/golden/junior` (profile title "Junior DevOps Engineer"):

- headline "Sr. DevOps Engineer · AWS"
- headline "Snr DevOps Engineer"
- summary with "Junior DevOps engineer" replaced by "Sr. DevOps engineer"

Treat `sr`/`snr` as `senior` and `jr`/`jnr` as `junior`. A source with the full word supports the abbreviation, and a
source with the abbreviation supports the full word.

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`: `SENIORITY_WORDS`, `_SENIORITY_RE`, `_check_seniority`.
- Existing tests: `tests/unit/test_provenance.py` from `test_unsupported_seniority_word_is_reported` (about line 348)
  onward.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py` (the seniority constants and `_check_seniority` only)
- `tests/unit/test_provenance.py`
- `plan/reports/WP-FIX-5-5.md`

## Steps

1. Add a module constant `SENIORITY_ALIASES = {"sr": "senior", "snr": "senior", "jr": "junior", "jnr": "junior"}`
   (casefolded). Include its keys in `_SENIORITY_RE` (whole word, so "Sr." matches "Sr" before the dot).
2. In `_check_seniority`, a word is supported when its canonical form (`SENIORITY_ALIASES.get(key, key)`) or any alias
   of that canonical form appears as a whole word in `source`. Keep deduplicating on the canonical form. Keep reporting
   the word as written in the text, with the unchanged rule-4 message
   (`headline t-header mentions 'Sr'; not found in refs [basics, exp-1]`).
3. Tests in `test_provenance.py`:
   - The 3 junior mutations above are reported as `unsupported_term`.
   - A summary "Sr. platform engineer …" passes when a cited item contains "Senior".
   - A summary "Senior platform engineer …" passes when a cited item contains "Sr.".
   - A summary naming "SR-IOV" passes when a cited item also names "SR-IOV", because the source has "sr" as a whole word.
   - The existing seniority tests and `test_golden_passes` still pass.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_provenance.py                                 # passes
uv run pytest -q tests                                                         # passes, 0 skipped, 0 xfailed
```
