# WP-I4 report: integrate wave 4

Status: DONE. Acceptance 3/3 pass. `uv run pytest -q tests/unit tests/integration`: 1197 passed, 1 skipped.

## Summary

- **Runner wiring:** `ApiRunner` (WP-22) already called `stages.run_stage_checked` with `AnthropicClient`. I changed
  it to build its client through `llm.default_client()`. That returns `FakeClient.from_dir($GTJOB_FAKE_LLM)` when the
  variable is set, otherwise `AnthropicClient()`. The hook is off by default.
- **`GTJOB_FAKE_LLM=<dir>`:** `FakeClient.from_dir` loads `<stage>.json` or `<stage>.N.json` (attempts in numeric
  order). A missing directory fails with `E_FAKE_LLM_DIR` and a missing stage file with `E_FAKE_EXHAUSTED`, both with
  hints. With the hook set, `ApiRunner` points the response cache at `<dir>/.cache/`, so canned answers never reach
  the real `.cache/gtjob/llm`. Documented only in `evals/README.md` and the tests.
- **Real bug found by the offline replay (sample scale):** `gtjob tailor --answers` with 8 round-1 questions plus a
  scope follow-up failed with `E_CHECK_FAILED: 9 pending checkpoint-1 questions; the limit is 8` (WP-20 feedback 4).
  The flow adds follow-ups before committing the round, so round 1 and round 2 counted together. Fix: the limit in
  `cvtlib/questions.py` is now per round. Regression tests are in `test_wave4.py`.
- **Guide feedback from WP-20** applied (wording only, below). `lint-skill --all` passes.
- **README:** removed the stale "gtjob is planned / not yet available" notes (WP-24 wrote them before the CLI existed).

## Files changed

- New: `tests/integration/test_wave4.py`, `plan/reports/WP-I4.md`.
- Cross-WP edits (all minimal):
  - `src/gtjob/llm.py`: `FAKE_LLM_ENV`, `FakeClient.from_dir`, `default_client` (WP-21).
  - `src/gtjob/cli.py`: `ApiRunner` uses `llm.default_client()` and the fake cache root (WP-22).
  - `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`: per-round pending limit (WP-15).
  - `README.md`: status note and "planned" labels removed (WP-24).
  - `evals/README.md`: `GTJOB_FAKE_LLM` section (WP-23).
  - `references/checkpoint-questions.md`, `answer-parsing.md`, `stage-tailor.md`, `commands.md`: guide fixes below.

## Guide changes from WP-20 feedback (wording; no contract change)

- Feedback 3 (`checkpoint-questions.md` rule 3): gap choices are ordered heaviest first. Requirements that ask for
  the same thing (SLOs and error budgets) may share one choice that links all `req_id`s. The 5-gap example is
  illustrative.
- Feedback 4 (`checkpoint-questions.md` Follow-ups): follow-ups are their own round, the cap of 8 is per round
  (matches the code fix), and `questions --add` is the only way to create one.
- Feedback 10 (`checkpoint-questions.md`): suppression never rewrites a prompt, so prompts should name only the choices
  offered.
- Feedback 5 (`answer-parsing.md`): one correction attestation changes one field, so a date range is one `date_text`
  correction. A skipped question is `skipped` and an unmentioned one is `defaulted`.
- Feedback 9 (`stage-tailor.md` rule 9): talking points are term-checked against refs, so an employer, certification,
  or term such as SOC 2 needs a ref to the item that contains it. A certificate does not support a skill. Attestations
  sit in the profile digest section.
- Feedback 1 (`commands.md`): the run id is date-prefixed and a bare suffix is not resolved.

Not applied (code or data, not wording): 2 (acceptance grep is in WP-20's own brief; use `"stage":"reported"`),
6 (profile and answer_parse packet budgets over for a 6-page CV), 7 (`profile-build` glues a label-only line into the
first skill), 8 (stale `E_CHECK_FAILED` left in `status` after a successful re-run), 11 (diff outline vs fit page
estimate). These need a fix-up WP or a decision at G4.

## Acceptance (logs in `.cache/logs/WP-I4/`)

```
uv run pytest -q tests/unit tests/integration        (all.log)
1197 passed, 1 skipped in 69.64s
uv run pytest -q evals --co -q >/dev/null && echo evals-collect-ok
evals-collect-ok
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all
lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile
```

`test_wave4.py` (12 tests, no key, no network):

- junior goldens as `GTJOB_FAKE_LLM` reach `reported` with `--answers`
- a checkpoint-2 instruction runs the `change_request` stage
- non-TTY run stops at checkpoint 1 (exit 6)
- missing stage file and bad directory give actionable errors
- numbered attempts order numerically
- the hook is off by default (`E_API_KEY`, exit 3)
- private sample replays through `cvt validate-artifact` (7 artifacts) and `validation.json` passes (ran, not skipped)
- private sample full offline run (8 questions + follow-up) reaches `reported`
- per-round pending limit
- README `gtjob` subcommands and flags exist, and `gtjob --help` / `cvt --help` work
- `evals` collect with no errors

## Deviations

- The `questions.py` change is outside the brief's literal list, but it is a bug fix that the brief's "wire the real runner"
  goal exposed; the gate reviewer should confirm that a per-round cap matches the contract's intent ("at most 8 in
  one batch"). `interfaces.md` only fixes `MAX_CP1_QUESTIONS = 8`, which is unchanged.
- The brief says "FakeClient"; the hook lives on `FakeClient.from_dir` plus `llm.default_client()`.

## Open issues

- No live API run was possible (no key). `ApiRunner` and `AnthropicClient` remain untested against the real API; WP-23's
  live evals are the check.
- WP-23 open question resolved: `evals/conftest.py::stage_env` finds `gtjob.config.load_config`, and `run_stage` returns the
  `answers.round.json` path. The `--answers` free-text target `q-1` in the live evals still assumes the gap question is `q-1`.
- Remaining WP-20 feedback items 2, 6, 7, 8 and 11 (above) are unfixed.
