# WP-FIX-3-6 report: articles before multipliers count as numbers

## Summary

- `a`, `an`, and `one` now count as the value 1 when a multiplier (`hundred`, `thousand`, `million`, `dozen`) follows
  directly, separated only by spaces or a hyphen. The run then yields 100, 1000, 1000000, or 12.
- Implementation: `_atoms` in `lexicon.py` emits a unit atom of value 1 for such an article. The new module constant
  `ARTICLE_MULTIPLIER_WORDS` names the article set. The existing `_parse_run` logic does the rest.
- A bare `a`/`an`/`one` not followed by a multiplier still yields nothing. `one of the first` → `[]`,
  `an outage` → `[]`, `twenty-one` → `21`, `a dozen runbooks` → `12`, `hundreds of hosts` → `[]`, digits unchanged.
- The four gate sentences now yield numbers (see below).

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py` (new constant `ARTICLE_MULTIPLIER_WORDS`, changed `_atoms`)
- `tests/unit/test_lexicon.py` (new cases in `test_numbers_normalization`, one existing case updated, see Deviations)
- `plan/reports/WP-FIX-3-6.md` (this report)

## Gate sentences: `lexicon.numbers(...)` output

```
'Scaled the platform to one million users.' ['1000000']
'Grew to a million requests per day.' ['1000000']
'Managed one hundred servers.' ['100']
'Ran a hundred servers.' ['100']
```

## Acceptance

### 1. `uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py`

Exit 0. Log: `.cache/logs/WP-FIX-3-6/ac1.log`

```
........................................................................ [ 36%]
........................................................................ [ 73%]
....................................................                     [100%]
196 passed in 10.81s
```

### 2. `uv run pytest -q tests/unit tests/integration` (first run)

Exit 1. Log: `.cache/logs/WP-FIX-3-6/ac2.log`

```
FAILED tests/unit/test_answers.py::test_correction_value_grounded_in_raw_text_passes
FAILED tests/unit/test_answers.py::test_correction_dry_run_line_shows_the_change
2 failed, 1017 passed, 1 skipped in 60.60s
```

### 2b. `uv run pytest -q tests/unit tests/integration` (rerun, same code)

Exit 0. Log: `.cache/logs/WP-FIX-3-6/ac2_rerun.log`

```
........................................................................ [ 98%]
............                                                             [100%]
1019 passed, 1 skipped in 59.34s
```

The two `test_answers.py` tests also pass on their own (`test_answers.py` file alone: 56 passed,
log `.cache/logs/WP-FIX-3-6/answers_file.log`). Both are in `answers.py` date-correction handling
(`exp-1.start_date: 2023-01 -> 2022-06`) and do not involve number words.

## Deviations

- Existing case `("hundreds of hosts, a hundred", [])` now expects `["100"]`. Under the new rule, `a hundred` is 100,
  which the brief requires. `hundreds of hosts` still yields nothing. I also added `("hundreds of hosts, an outage", [])`
  to keep the no-number intent covered.

## Open issues

- The first full-suite run failed 2 `tests/unit/test_answers.py` tests. The rerun on the same code passed 1019/1019,
  so the failure looks intermittent. Other workers are editing this checkout concurrently, and the cause is not
  confirmed. It is not caused by the lexicon change: the failing path is date-correction validation in `answers.py`,
  and the lexicon is a pure function with cached assets. Worth a look at the gate if it recurs.
- No ESCALATION: no contract change was needed, and the golden and fixture tests passed without editing them.
