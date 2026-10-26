# WP-FIX-2-4: `profile-build` verifies dates, locations, and degrees

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2) | WP-10, WP-I2, **user approval of `plan/reports/WP-G2-contract-change.md` C2** | Sonnet (`cv-builder`) | M |

Dispatch only after the orchestrator has applied C2 to `plan/contracts/interfaces.md`.

## Goal

Provenance rule 6 compares the tailored dates, location, and degree with `profile.json`, so the profile must itself be
verified against the CV. Gate probes on the junior `profile-map.json` that exit 0 today and must exit 1 with
`not_verbatim`:

| Mutation | CV says |
| --- | --- |
| work[0] `start_date: "2023-02"` (date_text unchanged) | `Feb 2024 - Present` |
| work[1] `end_date: "2025-01"` | `Jul 2023 - Dec 2023` |
| work[0] `location: "Austin, TX"` | `Columbus, OH` |
| education[0] `area: "Computer Engineering"` | `Computer Science` |

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract after C2: `sed -n '/^### WP-10 /,/^### /p' plan/contracts/interfaces.md`.
- `cvtlib/profile_map.py`: `build_profile` already has a builder with `check_in(value, lines, item_id, field)` (around
  line 157), which is used for `date_text`. Reuse it for the new verbatim fields.
- `cvtlib/profile.py`: `normalize_text` and `comparable` are used for matching, and `_month_index` parses `YYYY-MM`.
  `verify_verbatim` (around line 185) is the `profile-verify` path.
- Junior fixtures: `tests/fixtures/cv/jamie-rivera-junior.txt` and `tests/fixtures/golden/junior/profile-map.json`.
  The golden must still build a profile equal to `golden/junior/profile.json`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py` (a new date-consistency helper, called from
  `verify_verbatim`)
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_map.py`
- `tests/unit/test_profile_map.py`, `tests/unit/test_profile.py`
- `.claude/skills/tailoring-cvs/references/stage-profile.md` (the "Typed values" bullet, line 35, only)
- `plan/reports/WP-FIX-2-4.md`

## Steps

1. In `profile.py`, add `date_consistency(date_value: str, date_text: str) -> str | None`. It returns `None` when
   consistent, or a short reason otherwise. The rules:
   - `""` is always allowed.
   - `present` needs one of `Present`, `Current`, `Now`, `Today` (case-insensitive) in `date_text`.
   - `YYYY` needs the year in `date_text`.
   - `YYYY-MM` also needs the month as its English name, a 3-4 letter abbreviation (`Sep`, `Sept`), or its number
     (`2`, `02`).

   Put the month names in a module-level constant. Year matching must be whole-number, so `2023` does not match
   `12023`.
2. In `profile_map.build_profile`, for each work item and engagement with a non-empty `date_text`, check `start_date`
   and `end_date` with `date_consistency`. Report each failure as `not_verbatim`, for example:
   `exp-1: start_date '2023-02' is not consistent with date_text 'Feb 2024 - Present'`.
3. Also in `build_profile`, report `not_verbatim` when any of these is not found in its cited lines (case-insensitive
   after `normalize_text`):
   - `role_label`;
   - education `area` and `study_type`;
   - each comma-separated part of a work, engagement, or education `location`;
   - `basics` `city`, `region`, and `country`;
   - the year of an education `end_date` or a certificate `date`.

   Empty values are skipped.
4. Call `date_consistency` from `profile.verify_verbatim` for work and engagements as well (code `fact_mismatch`, as
   that function already uses).
5. Tests in `test_profile_map.py`: one test per mutation in the Goal table. Add positives for `Sept 2014 - March 2017`
   → `2014-09`/`2017-03`, `2019 - 2021` → `2019`/`2021`, and `Jan 2020 - Current` → `present`. Re-assert that the junior
   golden builds unchanged.
6. `stage-profile.md` line 35: add "role labels, degree area and type, location parts" to the list, and add one
   sentence: "Normalized dates must agree with `date_text`."

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py   # passes
uv run pytest -q tests/integration/test_wave2.py                             # passes (golden map still builds)
uv run pytest -q tests/unit tests/integration                                 # passes
```
