# WP-FIX-4-1: `live` tests are deselected unless asked for (no API calls from `pytest tests/unit`)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4) | WP-21, WP-I4 | Haiku (`cv-builder-lite`) | XS |

## Goal

`_COMMON.md` section 5 says unit tests must not use the network or the Anthropic API, and `README.md` says
`uv run pytest -q tests/unit` needs "no network, no API key". But `tests/unit/test_gtjob_llm.py::test_live_jd_stage_returns_schema_valid_jd`
is marked `@pytest.mark.live` and nothing deselects that marker by default. With `ANTHROPIC_API_KEY` exported, the plain
unit run calls the real API. The gate reproduced this: with a fake key and `ANTHROPIC_BASE_URL=http://127.0.0.1:9`,
`uv run pytest -q tests/unit/test_gtjob_llm.py` fails with `cannot reach the API after 3 retries`.

Make `live` tests run only when the command line selects them with `-m live`.

## Context

- Read `plan/tasks/_COMMON.md`. You may edit `pyproject.toml` for this fix only (the `[tool.pytest.ini_options]` table).
- pytest uses the last `-m` it sees, so `-m live` on the command line overrides an `-m "not live"` in `addopts`
  (the gate verified this: `pytest -m "not live" -m live tests/unit/test_gtjob_llm.py --co -q` collects 1 test).
- Documented commands that must keep working: `uv run pytest -q -m live tests/unit/test_gtjob_llm.py`,
  `uv run pytest -q evals -m live -x`, `uv run pytest -q evals -m "not live"`, `uv run pytest -q evals --co -q`.

## Owned files

- `pyproject.toml` (only `[tool.pytest.ini_options]`; do not touch dependencies, and do not run `uv lock` or `uv add`)
- `plan/reports/WP-FIX-4-1.md`

## Steps

1. In `[tool.pytest.ini_options]`, add `addopts = ["-m", "not live"]` (or the string form `addopts = "-m 'not live'"`).
   Keep `testpaths` and `markers` unchanged.
2. Run the acceptance commands. If any test outside your file asserts on collection counts and now fails, report it
   under `## ESCALATION` with the output. Do not edit other files.

## Acceptance criteria

```bash
ANTHROPIC_API_KEY=sk-fake-g4 ANTHROPIC_BASE_URL=http://127.0.0.1:9 uv run pytest -q tests/unit tests/integration   # passes; no live test runs
uv run pytest -q -m live tests/unit/test_gtjob_llm.py --co -q | tail -1      # "1/20 tests collected (19 deselected)" (or similar: exactly 1 selected)
uv run pytest -q -m live tests/unit/test_gtjob_llm.py                         # 1 skipped (no key)
uv run pytest -q evals -m "not live"                                          # passes
uv run pytest -q evals --co -q >/dev/null && echo evals-collect-ok
git diff --stat HEAD -- uv.lock | wc -l                                        # 0
```
