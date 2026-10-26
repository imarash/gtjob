# WP-FIX-2-6: title / role label seniority qualifiers

## Summary
- `profile.py`: added `SENIORITY_QUALIFIERS` (the 20 words from the brief), `TITLE_TOKEN_CHARS`, `TOKEN_TRIM_CHARS`,
  and `dropped_qualifier(value, text)`. It returns a reason such as `drops the qualifier 'junior'`, or `None`
  when the value is empty, absent, or has at least one occurrence with no qualifier beside it.
- `profile.verify_verbatim`: also checks work `position` and engagement `role_label` against the whole CV
  (code `fact_mismatch`, message `position 'X' drops the qualifier 'q' in cv.txt; copy the full position`).
- `profile_map.build_profile`: new `_Builder.check_qualifier`, called for `title` and `role label`. It reports
  `not_verbatim`: `exp-1: title 'DevOps Engineer' drops the qualifier 'junior' in its cited lines; copy the full title`.
- `stage-profile.md` "Typed values" bullet: appended the "Copy titles and role labels whole..." sentence.
- Tests: both Goal-table mutations, `Co-Founder`→`Founder`, `Assistant Manager`→`Manager`, a role-label case,
  positives (full titles, `Senior Engineer (Contract)` → `Senior Engineer`, once-with/once-without), a
  `dropped_qualifier` unit table, a `verify_verbatim` case. The existing golden-equality tests still pass.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_map.py`
- `.claude/skills/tailoring-cvs/references/stage-profile.md`
- `tests/unit/test_profile.py`, `tests/unit/test_profile_map.py`
- `plan/reports/WP-FIX-2-6.md`

## Acceptance
```
uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py
87 passed, 1 skipped in 0.47s            (.cache/logs/WP-FIX-2-6/a1.log)
uv run pytest -q tests/unit/test_refs_stages_a.py
16 passed in 0.06s                       (.cache/logs/WP-FIX-2-6/tests_unit_test_refs_stages_a.py.log)
uv run pytest -q tests/integration/test_wave2.py
5 passed in 4.90s                        (.cache/logs/WP-FIX-2-6/tests_integration_test_wave2.py.log)
uv run pytest -q tests/unit tests/integration
627 passed, 1 skipped in 26.92s          (.cache/logs/WP-FIX-2-6/full.log)
```

## Deviations
- `verify_verbatim` messages use the field label `position` / `role_label`. The contract only requires code
  `fact_mismatch`.
- Following the brief, only a trailing `-` or `.` is stripped from tokens. A leading hyphen on the token after the value
  (for example `Founder-Intern`) is not stripped, so that form is not caught.
- A bare common word such as `Senior` is not in the list, so `Senior Engineer` → `Engineer` still passes. This is
  per the brief's word list.

## Open issues
- None.
