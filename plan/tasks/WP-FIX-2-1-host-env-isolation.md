# WP-FIX-2-1: Isolate tests from the Cursor / Claude Code host environment

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2) | WP-I2 | Haiku (`cv-builder-lite`) | XS |

## Goal

`uv run pytest -q tests/unit tests/integration` fails inside Cursor (2 failures), so WP-I2's acceptance command and
every later worker's "unit suite still passes" check are red in the build's own environment. Cause:
`cvtlib.state.current_host()` now calls `cvtlib.hostdetect.detect()`, which returns `cursor` when any `CURSOR_*`
variable is set and `claude_code` when `CLAUDECODE` is set. The `workspace` fixture in `tests/conftest.py` clears only
`GTJOB_HOST`, so `tests/unit/test_state.py::test_create_run_layout` and `::test_host_detection_and_history` see
`cursor` instead of `unknown`.

Also undo a stray out-of-ownership edit: `tests/integration/__init__.py` gained one blank line in wave 2 (it was empty
in `HEAD`).

## Context

- Read `plan/tasks/_COMMON.md`.
- `tests/conftest.py` lines 19-31: `HOST_ENV = "GTJOB_HOST"` and the `workspace` fixture, which calls
  `monkeypatch.delenv(HOST_ENV, raising=False)`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/hostdetect.py`: the variables it reads.

## Owned files

- `tests/conftest.py` (the `workspace` fixture and one module-level constant only)
- `tests/integration/__init__.py`
- `plan/reports/WP-FIX-2-1.md`

## Steps

1. In `tests/conftest.py`, add a module-level constant next to `HOST_ENV`, for example
   `HOST_DETECT_ENV_PREFIXES = ("CURSOR_",)` and `HOST_DETECT_ENV_NAMES = ("CLAUDECODE",)`, matching what
   `hostdetect.py` reads.
2. In the `workspace` fixture, after the existing `delenv`, also `monkeypatch.delenv(name, raising=False)` for every
   name in `HOST_DETECT_ENV_NAMES` and for every key in `os.environ` that starts with a prefix in
   `HOST_DETECT_ENV_PREFIXES`. Iterate over `list(os.environ)`.
3. Make `tests/integration/__init__.py` empty again (0 bytes), identical to `HEAD`.
4. Do not change any test assertion and do not touch `hostdetect.py` or `state.py`.

## Acceptance criteria

Run these from a normal Cursor shell. Do **not** strip any environment variables.

```bash
uv run pytest -q tests/unit/test_state.py tests/unit/test_run_commands.py   # passes
git diff --exit-code HEAD -- tests/integration/__init__.py && echo "init restored"
uv run pytest -q tests/unit tests/integration > .cache/logs/FIX-2-1/suite.log 2>&1; tail -n 3 .cache/logs/FIX-2-1/suite.log   # 0 failed
```
