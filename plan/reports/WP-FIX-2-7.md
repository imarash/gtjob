# WP-FIX-2-7 report: `dropped_qualifier` catches a hyphenated qualifier after the title

## Summary

`cvtlib.profile.dropped_qualifier` trimmed the neighbouring tokens with `.rstrip(TOKEN_TRIM_CHARS)`, so a qualifier
hyphenated after the value kept its leading `-` (`-intern`) and never matched `SENIORITY_QUALIFIERS`. Changed both
calls to `.strip(TOKEN_TRIM_CHARS)`, updated the docstring to say a hyphen may separate the value from the neighbouring
token, and added three rows to the `test_dropped_qualifier_unit` table. Spaced dashes still return `None`.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py`: `dropped_qualifier` only (two `.strip` calls, docstring).
- `tests/unit/test_profile_map.py`: three rows added to the `test_dropped_qualifier_unit` parametrize table.
- `plan/reports/WP-FIX-2-7.md`: this report.

## Acceptance commands

Logs are in `.cache/logs/WP-FIX-2-7/`.

1. `uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py`: PASS (log `a1.log`)

```
..............................s......................................... [ 79%]
...................                                                      [100%]
90 passed, 1 skipped in 0.39s
```

2. `uv run pytest -q tests/integration/test_wave2.py`: PASS (log `a2.log`)

```
.....                                                                    [100%]
5 passed in 4.92s
```

3. Hyphen assertion script (prints `hyphen ok`): PASS (log `a3.log`)

```
hyphen ok
```

4. `uv run pytest -q tests/unit tests/integration`: PASS (log `a4.log`)

```
630 passed, 1 skipped in 26.83s
```

Note on the command 1 count: the gate's "92 passed, 1 skipped" for the same three test files predates the three new table rows. 90 + 5 = 95 passed, which matches 92 + 3.

## Deviations

None. Both files were already untracked in git (`?? `), so there is no tracked diff to show.

## Open issues

None.
