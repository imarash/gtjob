# WP-FIX-2-5 report: restore `tests/integration/__init__.py`

Status: DONE

## Summary

`tests/integration/__init__.py` was 1 byte (a newline) on disk. It is restored to the committed empty state.
`git diff --exit-code HEAD` now reports no difference for that file, and it no longer appears in `git status`.

## Files changed

- `tests/integration/__init__.py` (restored to the 0-byte `HEAD` blob)
- `plan/reports/WP-FIX-2-5.md` (this report)

## Deviation

The brief says to run `git checkout HEAD -- tests/integration/__init__.py`. The shared rules
(`_COMMON.md` section 2) and the worker rules forbid state-changing git commands, including checkout.
I used the read-only `git show HEAD:tests/integration/__init__.py > tests/integration/__init__.py`
instead. It writes the same committed content, which is 0 bytes.

## Acceptance commands

1. `git diff --exit-code HEAD -- tests/integration/__init__.py && echo "init restored"`
   ```
   init restored
   ```
   Result: PASS

2. `test "$(wc -c < tests/integration/__init__.py | tr -d ' ')" = 0 && echo "0 bytes"`
   ```
   0 bytes
   ```
   Result: PASS

3. `UV_CACHE_DIR=.cache/uv uv run pytest -q tests/unit tests/integration`
   Log: `.cache/logs/WP-FIX-2-5/pytest.log`
   ```
   ........................................................................ [ 11%]
   ........................................................................ [ 23%]
   ........................................................................ [ 35%]
   ..........s............................................................. [ 47%]
   ........................................................................ [ 59%]
   ........................................................................ [ 70%]
   ........................................................................ [ 82%]
   ........................................................................ [ 94%]
   .................................                                        [100%]
   608 passed, 1 skipped in 26.01s
   ```
   Result: PASS (608 passed, 1 skipped)

## Open issues

None for this WP. The one skipped test is a pre-existing skip (no sample CV or private fixture), not part of this fix.
