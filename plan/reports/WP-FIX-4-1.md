# WP-FIX-4-1 report: `live` tests deselected by default

## Summary

Added `addopts = ["-m", "not live"]` to `[tool.pytest.ini_options]` in `pyproject.toml`. Plain `pytest` runs
(`tests/unit`, `tests/integration`, `evals`) now skip `live`-marked tests, so no API call happens without an explicit
`-m live`. `-m live` on the command line overrides the default, as the brief expected. `testpaths`, `markers`,
dependencies, and `uv.lock` are unchanged.

## Files changed

- `pyproject.toml`: one line added in `[tool.pytest.ini_options]`.
- `plan/reports/WP-FIX-4-1.md`: this report.

## Acceptance commands

Run with `uv run --no-sync` (see Deviations). Logs are in `.cache/logs/WP-FIX-4-1/`.

1. `ANTHROPIC_API_KEY=sk-fake-g4 ANTHROPIC_BASE_URL=http://127.0.0.1:9 uv run --no-sync pytest -q tests/unit tests/integration`
   - Result: PASS, exit 0. `1197 passed, 1 deselected in 69.75s`. The deselected test is the live one.
   - Log: `.cache/logs/WP-FIX-4-1/a1.log`
2. `uv run --no-sync pytest -q -m live tests/unit/test_gtjob_llm.py --co -q | tail -1`
   - Result: PASS, exit 0. Output `tests/unit/test_gtjob_llm.py: 1`, so exactly 1 test is selected.
   - Log: `.cache/logs/WP-FIX-4-1/a2.log`
3. `uv run --no-sync pytest -q -m live tests/unit/test_gtjob_llm.py`
   - Result: PASS, exit 0. `1 skipped, 19 deselected in 2.20s` (no key in the environment, so the test skips).
   - Log: `.cache/logs/WP-FIX-4-1/a3.log`
4. `uv run --no-sync pytest -q evals -m "not live"`
   - Result: PASS, exit 0. `36 passed, 13 deselected in 2.54s`.
   - Log: `.cache/logs/WP-FIX-4-1/a4.log`
5. `uv run --no-sync pytest -q evals --co -q >/dev/null && echo evals-collect-ok`
   - Result: PASS, exit 0. Collection lists `evals/test_judge.py: 14` and `evals/test_triggers.py: 4`.
   - Log: `.cache/logs/WP-FIX-4-1/a5.log`
6. `git diff --stat HEAD -- uv.lock | wc -l`
   - Result: `0`. `uv.lock` is untouched.

Pass/fail: 6 of 6 acceptance checks pass.

## Deviations

- The brief's commands use `uv run`. Plain `uv run` failed in this sandbox with
  `failed to remove file .../bin/gtjob: Operation not permitted`. uv tries to re-sync the editable `gtjob` install,
  and the sandbox blocks removing a file outside the workspace. `uv run --no-sync` skips the re-sync and uses the
  existing `.venv`. No dependency or lock file was changed. Re-running plain `uv run` outside the sandbox should give
  the same results.
- `ANTHROPIC_API_KEY` was not set in the shell for check 3, so the live test skipped instead of calling the API.
  This is the expected result for that check.

## Open issues

None. No test outside this file asserted on collection counts that changed. The unit and integration suites
collect and pass with the new default.

## ESCALATION

None.
