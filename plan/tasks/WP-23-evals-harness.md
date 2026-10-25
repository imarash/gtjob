# WP-23: Live evals (interaction, judge vs baseline, triggering, consistency) and host checklist

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 | Waves 1-3; WP-21/22 contracts | Sonnet (`cv-builder`) | L |

## Goal

Build the evaluation harness that needs a real model: the soft gates (an LLM-as-judge rubric against a
no-skill baseline), the live canonical-exchange parse, skill triggering in Claude Code, a 3-run consistency
check, and the manual host checklist for Cursor and Claude Code.

## Context

- Read `plan/tasks/_COMMON.md`.
- Inputs:
  - Fixtures from WP-03: `tests/fixtures/expected/interaction-cases.yaml`, `evals/triggers.yaml`, the JDs.
  - The judge rubric from WP-05 (`references/critic-rubric.md`, including the baseline comparison section).
  - The CLI from WP-21/WP-22: `gtjob tailor --answers`, and `gtjob.stages.run_stage` for the single-stage parse.
- Live evals are marked `@pytest.mark.live`. They skip without `ANTHROPIC_API_KEY`, or without `claude` on PATH for
  trigger tests. They never run in the default `pytest` invocation (they are under `evals/`, which is not in
  `testpaths`).
- The sample CV is private, so sample cases skip when it is absent. The junior CV and the synthetic JDs always work.
- Claude Code headless: `claude -p "<query>" --output-format stream-json --verbose` emits tool-use events. A Skill
  tool invocation naming `tailoring-cvs` means "triggered". Run it from the repo root so project skills load. Use a
  scratch copy of the repo or a `--max-turns 1` style limit, so it never actually tailors. Verify the flags with
  `claude --help` and adapt.

## Owned files

- `evals/conftest.py`, `evals/test_interaction_live.py`, `evals/test_judge.py`, `evals/test_triggers.py`,
  `evals/test_consistency.py`
- `evals/judge.py` (rubric runner: Opus scores the tailored PDF text + PNGs + JD, and separately the baseline;
  writes `evals/results/<timestamp>/judge.json` and `summary.md`)
- `evals/baseline.py` (plain "Tailor my CV to this job description" prompt to Sonnet with the CV text + JD, with no
  skill or guides; the output rendered as Markdown for judging)
- `evals/HOST-CHECKLIST.md`
- `evals/README.md`
- `plan/reports/WP-23.md`

`evals/results/` is git-ignored by WP-01. Never write results anywhere else.

## Steps

1. `test_interaction_live.py`, for each case in `interaction-cases.yaml`:
   - Run `run_stage("answer_parse")` on the reply (after seeding a run with the golden checkpoint-1 questions; use
     the private sample if present, else skip sample-only cases).
   - Run `answers-apply --dry-run`/`--commit`.
   - Assert the expectations: claims, types, placements, scope kinds, resolved IDs, caveat presence, no forbidden
     numbers, exit code 6 for the ambiguous case.

   For `canonical`, also run the full CLI with `--answers` to the end and assert `final_cv` expectations against
   `tailored.json` and the PDF text, plus provenance passing with `att-` IDs cited. Then run the second JD and
   assert that `second_run_must_not_ask_about` terms are absent from pending questions.
2. `judge.py` + `test_judge.py`:
   - For the sample (if present) and the junior: tailored run vs baseline.
   - Scores 1-5 for relevance, impact, concision, readability, visual (from PNGs), truthfulness, and questions (the
     quality of checkpoint-1 questions, judged from `questions.json`). Each score has a justification.
   - Assert that the skill run has a mean score ≥ 4.0, no criterion ≤ 2, and truthfulness ≥ baseline.
   - Optional, with `GTJOB_EVAL_ALL_JDS=1`: also judge the sample CV against every real `JDs/*.md` (git-ignored, private).
     Report per-JD scores only in `evals/results/`.
   - Write a summary table.
3. `test_triggers.py`: for each query in `triggers.yaml`, assert triggered or not triggered.
   - Report precision and recall, and fail if recall < 0.9 or any negative triggers.
   - Run follow-up queries (such as "yes, add SLOs to the SRE roles") in a session seeded with an active run
     (`out/` contains a run at `awaiting_answers`).
4. `test_consistency.py`: run the junior pipeline 3 times with identical `--answers` and `--no-cache`. Assert the
   same set of selected engagements and roles, the same section order, the same page count, the same attestation
   claims, provenance passing every time, and a bullet count within ±2 per role.
5. `HOST-CHECKLIST.md`: a manual checklist with checkboxes for **Cursor** and **Claude Code**:
   - The core skill and the 5 commands appear under `/`.
   - Natural-language triggering works ("tailor my CV to JDs/staff-platform-sre.md").
   - The structured question tool is used at checkpoint 1.
   - The canonical reply typed in a later turn without the slash command resumes correctly.
   - `/cv-continue` works.
   - A run started in Cursor continues in Claude Code and in `gtjob continue`, and the reverse.
   - `cv-critic` runs read-only.
   - Custom Mode keeps the skill active.
   - The packaged zip uploads to claude.ai (optional).

   Include the exact prompts to type and the expected observations.
6. `evals/README.md`: how to run each eval, the cost estimate per run, and where results go.

## Token-efficiency requirements (interfaces.md section 14)

- **Token-budget eval** (live, opt-in):
  - Run the staff JD as a new-JD run on a cached profile.
  - Sum `usage.jsonl` actuals per stage.
  - Assert the total input ≤ 1.25 × the sum of the budget inputs, and the total output ≤ 1.25 × the sum of the
    budget outputs.
  - Report the cache-read share.
- The judge is text-first: PDF text + JD digest. Add PNGs only for the `visual` criterion, at 80 ppi, page images
  only.
- Write the results to `evals/results/<date>/tokens.json` along with the quality scores, so trade-offs are visible.

## Acceptance criteria

```bash
uv run pytest -q evals --co -q | tail -3       # collects tests without errors
uv run pytest -q evals -m "not live"           # passes (pure helpers only) or reports no tests
uv run pytest -q evals -m live -x              # passes or skips cleanly when no key/claude CLI
```

## Definition of done

The common definition of done. The report states which live evals were run (if a key was available) and their
results.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-23.md` under `## ESCALATION`. Do not change it.
