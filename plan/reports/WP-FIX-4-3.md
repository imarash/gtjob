# WP-FIX-4-3: judge reads validation gates by `name` and `status`

## Summary

`evals/judge.py::validation_summary` read `id`/`passed`/`ok`, which validation gates do not have, so every gate was
rendered as `fail`. It now reads each gate's `name` and `status` and prints `name=status` verbatim (`pass`/`warn`/`fail`/`skipped`).
The leading `pages: N; passed: X; gates: ` format is unchanged.

A new unmarked test, `test_validation_summary_reads_name_and_status`, builds a schema-shaped `validation` dict with three
gates (`pass`, `warn`, `fail`), validates it with `cvtlib.schemas.validate(..., "validation")`, and asserts the summary.
The test fails on the old code (it renders `schema=fail`).

## Files changed

- `evals/judge.py`: `validation_summary` only.
- `evals/test_judge.py`: one new unmarked test, plus `from cvtlib import schemas` import.
- `plan/reports/WP-FIX-4-3.md`: this report.

## Acceptance commands

### 1. `uv run pytest -q evals -m "not live"`

Run as `uv run --no-sync pytest -q evals -m "not live"` (see deviations). Log: `.cache/logs/WP-FIX-4-3/pytest-evals.log`

```
....................................                                     [100%]
36 passed, 13 deselected in 2.72s
exit=0
```

### 2. `uv run pytest -q evals --co -q >/dev/null && echo evals-collect-ok`

Run with `--no-sync`. Log: `.cache/logs/WP-FIX-4-3/collect.log`

```
evals/test_judge.py: 14
evals/test_triggers.py: 4
collect exit=0
```

### 3. Private sample validation summary

`tests/fixtures/private/sample/validation.json` exists. Log: `.cache/logs/WP-FIX-4-3/sample-summary.log`

```
pages: 2; passed: True; gates: schema=pass, provenance=pass, placeholders=pass, logistics_leak=pass, attestation_status=pass, page_count=pass, typography_floor=pass, ats_roundtrip=pass, keyword_coverage=warn, layout=pass
sample exit=0
```

The `keyword_coverage=warn` value matches the brief's expectation. The summary now reports gate statuses correctly.

## Deviations

- `uv run pytest` (without `--no-sync`) failed before running any tests. `uv` tried to resync `.venv` and could not remove
  `.venv/bin/gtjob` (`Operation not permitted` under the sandbox). I used `uv run --no-sync` with the existing environment.
  No environment files were changed by me.
- The test imports `cvtlib.schemas`. `evals/conftest.py` already puts the skill's `scripts/` dir on `sys.path`, so no
  path setup was needed.

## Open issues

- None for this WP. The `uv` resync failure is an environment issue. Running `uv sync` outside the sandbox would likely fix it,
  but I did not run it because it rewrites the shared environment.
