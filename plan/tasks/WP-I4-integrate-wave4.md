# WP-I4: Integrate wave 4 (sample golden, CLI AI layer, CLI interaction, evals, docs)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (after WP-20…WP-24, before G4) | WP-20…WP-24 | Sonnet (`cv-builder`) | M |

## Goal

Wire the real WP-21 stage runner into WP-22's flow, add the offline fake-model hook that wave 5 uses, and
fold WP-20's guide feedback into the reference guides.

## Context

- Read `plan/tasks/_COMMON.md` and every `plan/reports/WP-2[0-4].md`. Read WP-20's `## Guide feedback` carefully.
- You may make **minimal** fixes in wave 1-4 files. Guide fixes from WP-20 feedback are allowed as long as they
  clarify without changing the contract. List each one in your report.

## Owned files

- `tests/integration/test_wave4.py`
- Minimal fixes in wave 1-4 files (listed in your report), including:
  - `src/gtjob/flow.py` and `src/gtjob/cli.py`: the real runner wiring.
  - `src/gtjob/llm.py`: a `GTJOB_FAKE_LLM=<dir>` hook. When set, `FakeClient` loads `<dir>/<stage>.json` (or a list
    of attempts in `<stage>.N.json`) instead of calling the API. It is documented only in `evals/README.md` and
    tests, and is never active by default.
- `plan/reports/WP-I4.md`

## Steps

1. Wiring: `gtjob tailor` and `gtjob continue` use `gtjob.stages.run_stage_checked` with `AnthropicClient` by
   default, or `FakeClient` when `GTJOB_FAKE_LLM` is set.
2. `test_wave4.py`:
   - `GTJOB_FAKE_LLM` pointing at a directory built from the junior goldens → `gtjob tailor --answers` reaches
     `reported`.
   - The private sample goldens, if present: replay them through `cvt` (`validate-artifact` on each) and confirm
     `validation.json` passes.
   - `README.md` commands exist (`gtjob --help`, `cvt --help`).
   - `evals` collect with no errors.
3. Apply WP-20's guide feedback in `references/*.md` (wording only) and re-run `lint-skill --all`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit tests/integration                  # passes
uv run pytest -q evals --co -q >/dev/null && echo evals-collect-ok
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all
```

## Definition of done

The common definition of done. The report lists every cross-WP edit and each guide change applied from WP-20.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-I4.md` under `## ESCALATION`. Do not change it.
