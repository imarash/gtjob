# WP-FIX-2-5: Restore `tests/integration/__init__.py` to its committed (empty) state

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2 re-gate 1) | WP-FIX-2-1 | Haiku (`cv-builder-lite`) | XS |

## Goal

`tests/integration/__init__.py` is 0 bytes in `HEAD`. On disk it is 1 byte (a single newline). WP-FIX-2-1 was meant to
restore it, but at re-gate 1 its acceptance command `git diff --exit-code HEAD -- tests/integration/__init__.py` still
fails. This stray out-of-ownership edit must not reach the wave 2 commit.

Editor "write file" tools may save an empty file as a single newline. Use git to restore it instead.

## Context

- Read `plan/tasks/_COMMON.md`.
- Nothing else is needed. Do not touch any other file.

## Owned files

- `tests/integration/__init__.py`
- `plan/reports/WP-FIX-2-5.md`

## Steps

1. Run `git checkout HEAD -- tests/integration/__init__.py`. Do not use a file-writing tool for this file.
2. Confirm that it is 0 bytes: `wc -c tests/integration/__init__.py` prints `0`.
3. Write the report. Paste the decisive output line of each acceptance command.

## Acceptance criteria

```bash
git diff --exit-code HEAD -- tests/integration/__init__.py && echo "init restored"   # prints: init restored
test "$(wc -c < tests/integration/__init__.py | tr -d ' ')" = 0 && echo "0 bytes"   # prints: 0 bytes
uv run pytest -q tests/unit tests/integration                                       # passes
```
