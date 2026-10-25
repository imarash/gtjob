# WP-22: `gtjob` CLI commands and the terminal interaction model

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 | Waves 1-3; WP-21 API (contract only; built in parallel) | Sonnet (`cv-builder`) | L |

## Goal

Implement every `gtjob` command, with the same interaction model as the IDE: terminal prompts at both
checkpoints, free-text answers parsed the same way, `--answers` YAML for non-interactive runs, `--auto`, and
`gtjob continue` that resumes any run started in Cursor or Claude Code, and the reverse.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 12 (commands and the `--answers` YAML format are normative), section 6
  (lifecycle; the CLI drives the same stages and commands), section 7 (checkpoint protocol), and section 4 (exit
  codes).
- WP-21 is built in parallel. Code against its contract (`gtjob.stages.run_stage_checked`, `gtjob.llm.FakeClient`,
  `gtjob.config`). In your tests, inject a fake `stages` module through a `Runner` dependency rather than importing
  WP-21 internals. Integration (I-4) wires the real ones.
- Deterministic steps call `cvtlib` functions or `cvtlib.cli.main([...])` in-process. Never shell out to `cvt.py`.

## Owned files

- `src/gtjob/cli.py` (replaces the WP-01 stub; `argparse`; entry `main()`)
- `src/gtjob/flow.py` (`drive(run_dir, *, runner, io, answers=None, auto=False) -> int`; a stage loop that dispatches
  on `state.stage`)
- `src/gtjob/interact.py` (`TerminalIO` and `ScriptedIO`; question prompting with numbered choices and free text;
  checkpoint-2 diff review loop)
- `src/gtjob/answers_yaml.py` (parse and validate the `--answers` YAML; map it to host-tool-style selections and
  free text)
- `tests/unit/test_gtjob_cli.py`, `tests/unit/test_gtjob_flow.py`
- `plan/reports/WP-22.md`

## Steps

1. `flow.drive`: a loop of `st = state.load(run)` → act by stage, until `reported` or a user wait:
   - `initialized` → ingest.
   - `ingested` → `profile-cache --lookup`, else the `profile` stage (profile-map), then `profile-build`.
   - `profiled` → `jd`.
   - `jd_analyzed` → `match`.
   - `matched` → `questions`.
   - `awaiting_answers` → prompt (or `--answers` / auto), then `answer_parse` for free text, then `answers-apply
     --dry-run`. Show the mapping, confirm, add follow-ups, commit, and loop.
   - `answers_applied` → `tailor` (tailor-plan), then `assemble`.
   - `tailored` → `diff`.
   - `awaiting_approval` → show the diff. Inputs: `a` approve all; `r N` reject; `e N <text>`; or free text →
     `change_request` → `apply-edits` → loop. `approve` when done.
   - `approved` → `fit` (no PNGs; `--critic-visual` adds `--png`).
   - `rendered` → `validate`.
   - `validated` → optionally the `critic` stage (with `--critic`) → `critique-save`, then `report`.
2. `interact.TerminalIO`: renders questions with numbered choices and the default shown, accepts input like
   `1,3`, `a`, a blank line for the default, or free text. `ScriptedIO` reads from a list, for tests.
3. `answers_yaml`: validate the keys (`checkpoint1`, `followups`, `checkpoint2`, `default_rest`). Choice-id lists
   become a host_tool round directly (deterministic, without AI), and strings go through `answer_parse`. Unknown
   question IDs → exit 2.
4. The non-interactive stop from section 12: with stdin not a TTY and no input left for the pending checkpoint, print
   and exit 6 with state saved. `continue --text` routes the reply to `answer_parse` (checkpoint 1) or
   `change_request` (checkpoint 2) based on `state.stage`.
5. `cli.py` implements the section 12 commands. `tailor` = `cvtlib.state.create_run` + `drive`. `continue` = resolve
   the run + `drive`. `status`/`render`/`profile`/`package-skill` delegate to `cvtlib`. `edit` = the
   `change_request` stage + apply + diff + approve prompt + fit + validate + report. `main()` sets
   `os.environ.setdefault("GTJOB_HOST", "cli")` before doing anything, so state history records the CLI as host. If `importlib.util.find_spec("gtjob.web.serve")` is found, call its `register(subparsers)` (optional
   wave 6 web UI); otherwise there is no `serve` command.
6. Tests, with a fake runner whose stage functions copy junior golden files into the run dir:
   - Non-TTY `tailor` without answers stops at checkpoint 1 with exit 6, then `continue --text` resumes it.
   - A full `tailor --answers` run (YAML with choice IDs and one free-text answer) reaches `reported`.
   - `--auto` creates no attestations and has every question defaulted.
   - `continue` on a run left at `awaiting_answers` by a different process. Simulate it by writing the state the
     way an IDE agent would: `questions` run, then stop.
   - The checkpoint-2 review loop with `r 2` then `a`.
   - Bad YAML → exit 2.
   - The missing API key path → exit 3 with the hint (real runner, no key).

## Token-efficiency requirements (interfaces.md section 14)

- At the end of a run (or on a stop), print a per-stage usage table from `usage.usage_totals`: stage, model,
  input, cache read, and output, plus the total.
- Checkpoint display is compact:
  - Questions: one line each.
  - The diff in compact form (`--full` on request with `d`).
  - Never dump artifacts.
- `answers_yaml` choice lists go through the `--select` code path (`answers.select_round`, or call the command
  in-process). Do not build a second implementation.
- `flow` passes `interactive=True` to the stage runner when attached to a TTY (1-hour cache TTL).

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_gtjob_cli.py tests/unit/test_gtjob_flow.py   # passes
uv run gtjob --help                                                         # lists tailor, continue, status, render, edit, profile, package-skill
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-22.md` under `## ESCALATION`. Do not change it.
