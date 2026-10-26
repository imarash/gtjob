# WP-FIX-3-7 report: correction attestations grounded and shown in the dry run

Status: DONE

## Summary
- `answers._proposal_violations`: for a correction, every term in `lexicon.find_terms(correction.new_value)` (minus
  `common-words.txt`) must satisfy `lexicon.supports(term, grounding)`, with the same grounding text as WP-FIX-3-3
  (`raw_text` plus chosen option label/value). Failures give an `unsupported_term` violation at
  `items[i].attestations[j].correction.new_value`. The number check is unchanged.
- A correction with any non-blank `terms` entry is now a `schema` violation: "a correction carries no terms; put the
  new value in correction.new_value". So it can no longer suppress a gap question via `find_by_terms`.
- Plan entries now carry `correction`. The `plan_table` `+ correction …` line appends
  ` <item_id>.<field>: <old> -> <new>`, with each value clipped to `CORRECTION_VALUE_WIDTH` (60) and `…`.
  The table stays ≤ 15 lines.
- New helper `_correction_term_violations` and constants `CORRECTION_VALUE_WIDTH`, `CORRECTION_TERMS_MESSAGE`.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py` (replaced `test_corrections_skip_the_term_check` with `test_grounded_correction_round_passes`;
  added 4 tests)
- `plan/reports/WP-FIX-3-7.md`

## Acceptance
`uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py` (log `.cache/logs/WP-FIX-3-7/a.log`)
```
86 passed in 10.49s
```
`uv run pytest -q tests/integration/test_wave3.py` (log `.cache/logs/WP-FIX-3-7/b.log`)
```
8 passed in 14.19s
```
`uv run pytest -q tests/unit tests/integration` (log `.cache/logs/WP-FIX-3-7/c.log`)
```
1019 passed, 1 skipped in 59.92s
```

## New tests
- `test_ungrounded_correction_values_are_rejected`: text on `sum-1` names `Kubernetes` and `Walmart`; position
  "Principal Kubernetes Architect" names `Kubernetes`. Both have code `unsupported_term` with the `correction.new_value` path.
- `test_correction_with_terms_is_a_schema_violation`
- `test_correction_value_grounded_in_raw_text_passes` ("my title at Quillmark was Principal Kubernetes Architect")
- `test_correction_dry_run_line_shows_the_change`: `exp-1.start_date: 2023-01 -> 2022-06`, truncation with `…`, ≤ 15 lines.
- `round-correction.json`, the golden rounds, `round-*.json` and the `--select` parity test still pass; no fixture was edited.

## Deviations
- The gate scenarios use a correction `claim` without numbers ("fix a bullet"). A claim such as "Quillmark start date is
  2022-06" already trips the existing number check when `raw_text` lacks that number, which is existing behaviour.

## Open issues
- None. The correction `claim` text itself is not term-checked (it is a label; only `new_value` becomes a profile fact).
