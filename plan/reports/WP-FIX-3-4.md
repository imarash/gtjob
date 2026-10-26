# WP-FIX-3-4 report: attestation suppresses a gap choice when it covers any synonym

Status: DONE (both acceptance commands pass)

## Summary

- `questions.py` now separates the two gap-choice value kinds:
  - `term|synonym` values are suppressed when an active attestation covers **any** part. The covering attestations of the first part that hits are used.
  - `req-N` values still need **every** requirement keyword covered.
- New helpers: `_covering_any`, `_choice_covering`. `_covering` is renamed to `_covering_all`.
- Suppression reason format (`answered by att-001 (Helm)`) and `data.suppressed` are unchanged.
- Tests:
  - Golden `junior/questions.json` + active `Helm` attestation suppresses `helm`, keeps `python_bash`.
  - Proposed `Helm` attestation does not suppress.
  - `req-N` with two keywords is not suppressed when only one is covered.
  - The old "partly covered" test asserted the all-parts rule, so it was split (see deviations).

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`
- `tests/unit/test_questions.py`
- `plan/reports/WP-FIX-3-4.md` (this file)

## Acceptance commands

### 1. `uv run pytest -q tests/unit/test_questions.py tests/unit/test_answers.py`

Exit 0. Log: `.cache/logs/WP-FIX-3-4/ac1.log`

```
82 passed in 10.19s
```

### 2. `uv run pytest -q tests/unit tests/integration`

Exit 0 (re-run after the other worker finished `answers.py`). Log: `.cache/logs/WP-FIX-3-4/ac2.log`

```
995 passed, 1 skipped in 57.70s
```

## Deviations

- Rewrote `test_suppression_ignores_proposed_and_partly_covered_choices` into two tests: `test_suppression_ignores_proposed_attestations` and `test_suppression_of_synonym_value_needs_any_part_covered`. The old test asserted that a partly covered `term|synonym` choice is kept. That is exactly the all-parts rule this WP removes. The new test expects the `slo` choice to be suppressed (5 choices remain).
- Added the golden-Helm tests and the partial `req-N` test listed in the brief.

## Open issues

None. The earlier `test_dry_run_line_shows_multi_term_attestations` failure was another worker's in-flight `answers.py` change and no longer reproduces.
