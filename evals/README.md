# Live evals

Evals that need a real model. They are not in `testpaths`, so plain `uv run pytest` never runs them. All live tests are
marked `live`; they skip cleanly when their credential is missing. Results go to `evals/results/<run id>/`
(git-ignored; the run id is a timestamp, or `GTJOB_EVAL_RUN_ID`).

| Eval | File | Needs | Notes |
| --- | --- | --- | --- |
| Interaction cases | `test_interaction_live.py` | `ANTHROPIC_API_KEY`, private sample (CV, `JDs/staff-platform-sre.md`, `tests/fixtures/private/sample/*.json`) | `answer_parse` on each reply, `answers-apply`, then the canonical end-to-end run and a second JD |
| Judge vs baseline | `test_judge.py` | `ANTHROPIC_API_KEY` (junior always; sample if present) | Writes `judge.json`, `summary.md`, `<case>.baseline.md` |
| All real JDs (opt-in) | `test_judge.py` | `GTJOB_EVAL_ALL_JDS=1`, sample CV, `JDs/*.md` | Per-JD scores stay in `evals/results/` |
| Token budget (opt-in) | `test_judge.py` | `GTJOB_EVAL_TOKENS=1`, sample CV, private sample | Writes `tokens.json` with quality scores |
| Skill triggering | `test_triggers.py` | `claude` on PATH and logged in | Writes `triggers.json` (precision, recall) |
| Consistency | `test_consistency.py` | `ANTHROPIC_API_KEY` | 3 junior runs, identical answers, `--no-cache` |

The unmarked tests in these files check the harness itself (parsers, scoring, gates, fingerprints, and a replay of the
golden rounds through the real `cvt answers-apply`). They need no key and no network.

## Running

```bash
uv run pytest -q evals --co -q | tail -3          # collection check
uv run pytest -q evals -m "not live"              # harness self-tests, no key needed
export ANTHROPIC_API_KEY=...                      # never commit it
uv run pytest -q evals -m live -x                 # everything live that has its inputs
uv run pytest -q evals/test_triggers.py -m live   # triggering only (uses your `claude` login)
GTJOB_EVAL_TOKENS=1 uv run pytest -q evals/test_judge.py -m live -k token
GTJOB_EVAL_ALL_JDS=1 uv run pytest -q evals/test_judge.py -m live -k all_jds
```

## What each eval asserts

- **Interaction** (`test_answer_parse_live[case]`): claims, types, placements, scope kinds, role labels, caveats, no
  invented numbers (the round); resolved item IDs, usable counts, follow-up questions, exit code 6 for the ambiguous case
  (after `--commit`). `followup_skip` first applies the canonical exchange so scope follow-ups are open.
  `test_canonical_end_to_end_and_second_jd` runs `gtjob tailor --answers`, checks `tailored.json` and PDF text, validation
  with provenance passing and active `att-` IDs cited, then a second JD that stops at checkpoint 1 and must not re-ask
  service mesh, Istio, or TypeScript. `test_edit_earlier_end_to_end` applies "drop the Earlier experience line" at
  checkpoint 2. Final-CV checks for `rejection` and `ambiguous_scope` are covered by the deterministic suites; these
  evals do not run a full pipeline for them.
- **Judge** (`judge.py`, rubric from `references/critic-rubric.md`): Opus scores the tailored PDF text (plus a text-only
  JD digest and the checkpoint-1 questions; page PNGs at 80 ppi only for `visual`) and, in a separate call, the
  baseline (`baseline.py`: plain "Tailor my CV to this job description." to Sonnet, no skill). Gates: mean >= 4.0, no
  criterion <= 2, truthfulness >= baseline. The baseline is scored on the five text criteria (it has no layout and no
  checkpoint); the winner weighs truthfulness first.
- **Token budget**: the staff JD as a new-JD run on a cached profile; sums `usage.jsonl` API lines per stage; total
  input (uncached + cache read + cache write) <= 1.25 x the sum of the budget inputs of the stages that ran, same for
  output. Reports the cache-read share.
- **Triggering**: each `triggers.yaml` query runs `claude -p` in a scratch copy of `.claude/` with tools limited to
  `Skill,Read`, so it can never tailor anything. Triggered = `Skill` call naming `tailoring-cvs` or a `Read` of its
  `SKILL.md`. Follow-up queries run with a run at `awaiting_answers` in `out/`. Fails on any false positive or recall < 0.9.
- **Consistency**: same selected engagements and roles, section order, page count, attestation claims; provenance passes
  every run; bullets per role within +-2.

## Cost (rough, Oct 2026 list prices; check your usage dashboard)

| Run | Model calls | Estimate |
| --- | --- | --- |
| Interaction, per case | 1 Haiku `answer_parse` | under $0.01 |
| Canonical end-to-end + second JD | full pipeline x2 (profile cached for the second) | $0.50 - $1.00 |
| Edit-earlier | full pipeline | $0.30 - $0.60 |
| Judge, per CV | 1 full pipeline + 1 Sonnet baseline + 2 Opus judge calls | $0.60 - $1.50 |
| Consistency | 3 junior pipelines | $0.60 - $1.20 |
| Triggering | 18 `claude -p` queries, each capped by `--max-budget-usd 0.50` | $0.20 - $1.00 (your Claude plan) |
| Token budget | 1 pipeline on a cached profile | $0.30 - $0.60 |
| All real JDs sweep | pipeline + baseline + judge per JD | about $1 per JD |

A full `-m live` run is roughly $3 - $7. Use `-k` to select one eval while iterating.

## Files

- `conftest.py`: workspace, `Cvt` runner, seeding (golden artifacts, no model), `gtjob` runner, skip fixtures.
- `judge.py`, `baseline.py`: rubric runner and baseline; importable and unit-tested without a key.
- `HOST-CHECKLIST.md`: the manual Cursor and Claude Code checklist.

## Offline replay (`GTJOB_FAKE_LLM`)

Test-only hook, never active by default. When `GTJOB_FAKE_LLM=<dir>` is set, `gtjob tailor` and `gtjob continue`
use `FakeClient` instead of the Anthropic API. It reads `<dir>/<stage>.json` (one attempt) or `<dir>/<stage>.N.json`
(attempts in order of `N`, for example a failing answer followed by a fixed one), where `<stage>` is `profile`, `jd`,
`match`, `questions`, `answer_parse`, `tailor`, `change_request` or `critic`. Each file holds that stage's output (for
example the junior golden `profile-map.json` is `profile.json`). No key is needed. The response cache for these runs
lives in `<dir>/.cache/`, so canned answers never reach the real cache. See `tests/integration/test_wave4.py`.
