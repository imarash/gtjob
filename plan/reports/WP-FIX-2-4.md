# WP-FIX-2-4: `profile-build` verifies dates, locations, and degrees

## Summary
- `profile.py`: new `date_consistency(date_value, date_text) -> str | None` (plus `has_year`, whole-number year match, and
  constants `MONTH_FULL_NAMES`, `MONTH_ABBREVIATION_LENGTHS`, `PRESENT_WORDS`). `verify_verbatim` now also reports
  `fact_mismatch` when a work item's (or an engagement's, if it ever carries one) `start_date`/`end_date` disagrees with
  its `date_text`.
- `profile_map.build_profile` now reports `not_verbatim` for: date inconsistency with `date_text` (work/engagements);
  `role_label` (already checked, kept); education `area` and `study_type`; each comma-separated part of work/education
  `location`; `basics` `city`/`region`/`country`; the year of an education `end_date` and a certificate `date`.
  Empty values are skipped. Message form: `exp-1: start_date '2023-02' is not consistent with date_text 'Feb 2024 - Present' (year 2023 not in date_text)`.
- All four gate mutations from the brief now produce `not_verbatim`; the junior golden still builds unchanged.
- `stage-profile.md` line 35 updated.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_map.py`
- `tests/unit/test_profile_map.py`, `tests/unit/test_profile.py`
- `.claude/skills/tailoring-cvs/references/stage-profile.md`
- `plan/reports/WP-FIX-2-4.md`

## Acceptance
```
uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py
68 passed, 1 skipped in 0.30s            (log: .cache/logs/WP-FIX-2-4/a1.log)

uv run pytest -q tests/integration/test_wave2.py
5 passed in 4.72s                        (log: .cache/logs/WP-FIX-2-4/a2.log)

uv run pytest -q tests/unit tests/integration
608 passed, 1 skipped in 26.76s          (log: .cache/logs/WP-FIX-2-4/a3.log)
```
3/3 pass.

## Deviations
- Existing parametrized test `test_not_verbatim_typed_values` case `work[0].date_text = "Feb 2020 - Present"` asserted exactly one
  violation. It now yields two (date_text not in lines, plus the unchanged `start_date 2024-02` disagreeing with the new
  `date_text`), which is correct behavior. The test now expects 2 for that case.
- Brief says to check "engagement" dates; the profile-map schema gives engagements no `date_text`/dates, so that branch
  is a no-op today (guarded by key presence).

## Open issues
- Date consistency is a per-value check, not positional: `start_date 2020-12` passes against `Jan 2020 - Dec 2021`
  because "Dec" appears in the text. Catching this would need parsing the range (not in the C2 contract).
