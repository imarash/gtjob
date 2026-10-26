# WP-FIX-2-1 report: isolate tests from host environment

## Summary

- `tests/conftest.py`: the `workspace` fixture now also clears host-detection inputs. It deletes `CLAUDECODE` and every
  `os.environ` key starting with `CURSOR_`, in addition to `GTJOB_HOST`. The two prefixes are module-level constants
  (`HOST_DETECT_ENV_PREFIXES`, `HOST_DETECT_ENV_NAMES`), matching `cvtlib/hostdetect.py`.
- `tests/integration/__init__.py`: restored to 0 bytes, identical to `HEAD` (stray blank line removed).
- No test assertions changed. `hostdetect.py` and `state.py` untouched.
- Acceptance commands were run from the Cursor agent shell, which exports `CURSOR_*` variables; no variables were stripped.
  Before the fix, `test_state.py` and `test_run_commands.py` depended on this host state.

## Files changed

- `tests/conftest.py`
- `plan/reports/WP-FIX-2-1.md` (this report)

`tests/integration/__init__.py` is no longer modified relative to `HEAD`.

## Acceptance commands

### 1. `uv run pytest -q tests/unit/test_state.py tests/unit/test_run_commands.py`

Result: pass (52 passed). Log: `.cache/logs/FIX-2-1/focused.log`

```
....................................................                     [100%]
52 passed in 5.36s
```

### 2. `git diff --exit-code HEAD -- tests/integration/__init__.py && echo "init restored"`

Result: pass. Output: `init restored`

### 3. `uv run pytest -q tests/unit tests/integration > .cache/logs/FIX-2-1/suite.log 2>&1; tail -n 3 ...`

Result: pass (575 passed, 1 skipped, 0 failed). Log: `.cache/logs/FIX-2-1/suite.log`

```
........................................................................ [ 87%]
........................................................................ [100%]
575 passed, 1 skipped in 26.64s
```

The 1 skip is the pre-existing private-sample-CV skip (`sample_cv_path` fixture when `CVs/ArashMorattab-CV-2026-10.pdf`
is absent); it is not related to this fix.

### 4. `uv run pytest -q tests/unit` (definition of done)

Covered by the full run above (`tests/unit` is included in acceptance 3).

## Deviations

- Commands were run with `UV_CACHE_DIR=.cache/uv` as permitted by `_COMMON.md` section 5 (sandbox cache write).
- The `run_cvt` fixture in `tests/conftest.py` was not changed. It still inherits the parent environment, including
  `CURSOR_*` variables, when it spawns `cvt.py` as a subprocess. The focused and full suites pass with that behaviour,
  and the brief limited edits to the `workspace` fixture, so it was left alone.

## Open issues

- None for this WP. If a future test asserts on the subprocess host (via `run_cvt`) under a Claude Code or Cursor host,
  it may need the same clearing applied to `run_cvt`'s `env`.
