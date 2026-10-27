# WP-FIX-4-3: the judge reads validation gates by `name` and `status`

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4) | WP-23 | Haiku (`cv-builder-lite`) | XS |

## Goal

`evals/judge.py::validation_summary` reads `gate.get('id', gate.get('name'))` and `gate.get('passed', gate.get('ok'))`.
Gates in `validation.json` (contract `validation.schema.json`) have `name` and `status` (`pass` | `warn` | `fail`), and
no `passed` or `ok`. So the judge is told that every gate failed. On the private sample, where `validation.passed` is
`true`, the gate saw:

```text
pages: 2; passed: True; gates: schema=fail, provenance=fail, placeholders=fail, ... keyword_coverage=fail, layout=fail
```

That summary goes into the Opus judge's input, so it biases the tailored-vs-baseline comparison.

## Context

- Read `plan/tasks/_COMMON.md`.
- `plan/contracts/validation.schema.json`: the gate object fields.

## Owned files

- `evals/judge.py` (only `validation_summary`)
- `evals/test_judge.py` (one new unmarked test)
- `plan/reports/WP-FIX-4-3.md`

## Steps

1. In `validation_summary`, print `name=status` for each gate, using the gate's `status` value verbatim
   (`pass`/`warn`/`fail`). Keep the leading `pages: N; passed: X; gates: ` format.
2. Add an unmarked test in `evals/test_judge.py` with a schema-shaped `validation` dict (three gates: `pass`, `warn`,
   `fail`). Assert that the summary contains `schema=pass`, `keyword_coverage=warn`, and `layout=fail`. Validate the
   dict against the `validation` schema first (use `cvtlib.schemas.validate` as other tests do), so the test breaks if
   the shape drifts.

## Acceptance criteria

```bash
uv run pytest -q evals -m "not live"           # passes
uv run pytest -q evals --co -q >/dev/null && echo evals-collect-ok
```

If `tests/fixtures/private/sample/validation.json` exists, paste the output of:

```bash
uv run python -c "import sys,json; sys.path.insert(0,'evals'); import judge; print(judge.validation_summary(json.load(open('tests/fixtures/private/sample/validation.json')), 2))"   # schema=pass ... keyword_coverage=warn
```
