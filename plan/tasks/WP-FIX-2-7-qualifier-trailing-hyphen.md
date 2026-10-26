# WP-FIX-2-7: `dropped_qualifier` also catches a qualifier hyphenated after the title

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2 re-gate 2) | WP-FIX-2-6 | Haiku (`cv-builder-lite`) | XS |

## Goal

Contract C3 (`plan/contracts/interfaces.md`, section 5, WP-10 block) says a title or role label fails when the word
directly before or after it, with "only spaces or a hyphen in between", is a seniority qualifier left out of the value.
`cvtlib.profile.dropped_qualifier` handles the hyphen only on the left. On the right, the token keeps its leading
hyphen (`-intern`), so it never matches `SENIORITY_QUALIFIERS`. Normalization maps an en or em dash to `-`, so this also
misses unspaced dashes. Today these return `None`, and they must return `drops the qualifier 'intern'`:

| value | text |
| --- | --- |
| `Software Engineer` | `Software Engineer-Intern` |
| `Software Engineer` | `Software Engineer\u2013Intern` (unspaced en dash) |

A spaced dash (`Software Engineer - Intern`) is still a separator and must still return `None`.

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py`, `dropped_qualifier` (around lines 85-112). The two tokens
  are built with `.rstrip(TOKEN_TRIM_CHARS)`.
- `tests/unit/test_profile_map.py`, `test_dropped_qualifier_unit` and its `parametrize` table (around line 400).
- The gate verified this change by monkeypatching: all of `test_profile.py`, `test_profile_map.py`, and `test_wave2.py`
  still pass (92 passed, 1 skipped).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py` (`dropped_qualifier` only: two calls and its docstring)
- `tests/unit/test_profile_map.py` (the `test_dropped_qualifier_unit` table only)
- `plan/reports/WP-FIX-2-7.md`

## Steps

1. In `dropped_qualifier`, change both `.rstrip(TOKEN_TRIM_CHARS)` calls to `.strip(TOKEN_TRIM_CHARS)`. Change nothing
   else in the logic.
2. In the docstring, replace "Only spaces may separate the value from the neighbouring token" with "Only spaces or a
   hyphen may separate the value from the neighbouring token".
3. Add three rows to the `test_dropped_qualifier_unit` table:
   - `("Software Engineer", "Software Engineer-Intern", "drops the qualifier 'intern'")`
   - `("Software Engineer", "Software Engineer\u2013Intern", "drops the qualifier 'intern'")`
   - `("Software Engineer", "Software Engineer - Intern", None)`
4. Write the report. Paste the decisive output line of each acceptance command.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py   # passes
uv run pytest -q tests/integration/test_wave2.py                             # passes (golden map still builds)
uv run python -c "import sys; sys.path.insert(0, '.claude/skills/tailoring-cvs/scripts'); from cvtlib.profile import dropped_qualifier as d; assert d('Software Engineer', 'Software Engineer-Intern'); assert d('Software Engineer', 'Software Engineer\u2013Intern'); assert d('Software Engineer', 'Software Engineer - Intern') is None; assert d('Founder', 'Co-Founder'); print('hyphen ok')"   # prints: hyphen ok
uv run pytest -q tests/unit tests/integration                                 # passes
```
