# WP-FIX-1-4 report: drop the `--visual` allowlist entry

## Summary

Removed the two comment lines and the `--visual` entry from `UNDOCUMENTED_FLAGS` in
`tests/integration/test_wave1.py`. The allowlist is now an empty typed tuple, so
`test_reference_flags_exist_in_section_3` checks every reference flag against section 3 with no exceptions.
The edit was re-read on disk before this report was written (line 61).

## Files changed

- `tests/integration/test_wave1.py` (lines 61-63 before the edit, now line 61 only)
- `plan/reports/WP-FIX-1-4.md` (this file)

## Acceptance commands

Log directory: `.cache/logs/WP-FIX-1-4/`

1. `grep -n "UNDOCUMENTED_FLAGS = \|UNDOCUMENTED_FLAGS: " tests/integration/test_wave1.py`
   ```
   61:UNDOCUMENTED_FLAGS: tuple[str, ...] = ()
   ```
   Pass: one line, ending in `= ()`.

2. `grep -c -- '"--visual"' tests/integration/test_wave1.py`
   ```
   0
   ```
   Pass: count is 0. (grep exits 1 when there are no matches, which is expected here.)

3. `uv run pytest -q tests/integration/test_wave1.py -k flags`
   Log: `.cache/logs/WP-FIX-1-4/flags.log`
   ```
   exit=0
   .                                                                        [100%]
   1 passed, 60 deselected in 0.11s
   ```
   Pass.

4. `uv run pytest -q tests/unit tests/integration`
   Log: `.cache/logs/WP-FIX-1-4/unit-integration.log`
   ```
   ........................................................................ [ 25%]
   ........................................................................ [ 50%]
   ........................................................................ [ 75%]
   ......................................................................   [100%]
   286 passed in 2.54s
   ```
   Pass (286 passed, matching the brief).

Commands were run with `UV_CACHE_DIR=.cache/uv`.

## Deviations

None. The brief's text was followed as written. The brief's own comment-line wording differed slightly from the file, but the file matched the brief's quoted lines and both were removed.

## Open issues

None.

## ESCALATION

None.
