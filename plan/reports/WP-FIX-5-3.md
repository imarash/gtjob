# WP-FIX-5-3 report: multiplier words count as numbers

Status: DONE (one failure outside owned files, see Open issues).

## Summary
`lexicon.numbers()` now emits tokens for multiplier words, so `provenance.check_tailored` flags invented
"tripling", "doubling", "halving", "tenfold" as `unsupported_number`.
- New constants `FOLD_SUFFIX`, `HALF_VALUE`, `SOLO_VALUE_WORDS` and atom kind `_KIND_SOLO`.
- `doubled|doubling|doubles` and `twofold` -> 2; `tripled|tripling|triples` and `threefold` -> 3;
  `quadrupled|quadrupling|quadruples` and `fourfold` -> 4; `<unit|tens|hundred>fold` -> its value;
  `half|halved|halving|halves` -> 50. Bare `double`/`triple` are not mapped.
- Solo atoms never join a run (`_joins` now takes the next atom and rejects solo on either side;
  `_parse_run` flushes and appends the value directly).
- `numbers()` docstring updated.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py` (each form, negatives `double-check`, `triple-A`, `on behalf of`, `doubledown`,
  no-join cases, and `provenance.check_tailored` cases: halved vs "50%" passes, doubled without a 2 fails,
  doubled vs "2x" passes, the four WP-G5 probe suffixes all flagged)
- `plan/reports/WP-FIX-5-3.md`

## Acceptance
`uv run --no-sync pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py`
(log `.cache/logs/WP-FIX-5-3/unit.log`)
```
1 failed, 208 passed in 0.50s
FAILED tests/unit/test_provenance.py::test_seniority_word_supported_by_a_ref_passes
  TypeError: check_tailored() missing 1 required keyword-only argument: 'draft'
```

`uv run --no-sync pytest -q tests` (log `.cache/logs/WP-FIX-5-3/all.log`)
```
FAILED tests/unit/test_provenance.py::test_seniority_word_supported_by_a_ref_passes
1 failed, 1325 passed, 1 deselected, 2 xfailed in 152.96s (0:02:32)
```
No golden kept-bullet or e2e test fails because of the lexicon change.

## Deviations
- Used `uv run --no-sync` (sandbox cannot rewrite `.venv/bin/gtjob`).
- Provenance cases live in `test_lexicon.py` because `test_provenance.py` is not an owned file.

## Open issues
- `test_provenance.py::test_seniority_word_supported_by_a_ref_passes` fails with a `TypeError` about a missing
  `draft` argument. `provenance.py` and `test_provenance.py` show as modified in `git status` and are not
  owned by this WP, so another worker's in-flight edit probably caused it. It does not involve `numbers()`.
  Re-run once that WP lands.
- "half" also maps to 50 in phrases like "half a million" (emits 50 and 1000000), per the brief; the same
  tokens arise from source text, so it is symmetric.
