# WP-08: Run commands (`init`, `status`)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01 | Sonnet (`cv-builder`) | S |

## Goal

Implement `cvt init` and `cvt status`, the entry and resume points that every host uses. `status`
must give any agent, in any host or later chat turn, everything it needs to continue a run.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 2 (run slug rules), section 3 (`init` and `status` rows), section 4 (envelope),
  section 6 (lifecycle, `next_action`), and `state.schema.json`.
- Use `cvtlib.state.create_run`, `load`, and `next_action_for`, and `cvtlib.paths.resolve_run` / `latest_run`
  from WP-01. Do not reimplement them.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/run.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/hostdetect.py`
- `tests/unit/test_run_commands.py`
- `plan/reports/WP-08.md`

## Steps

1. `init`:
   - Arguments exactly per section 3. Exactly one JD source is required (exit 2 otherwise).
   - `--jd-stdin` reads stdin.
   - Validate that the CV exists and its extension is pdf/txt/md/docx (exit 5 otherwise; docx is
     accepted only if WP-28 is present, so for now docx exits 5 with the hint "export to PDF or paste
     text").
   - Call `state.create_run`. Print the slug, the run dir, and `next_action`.
   - `--json`: `data = {run_dir, run_slug, inputs}`.
2. `hostdetect.py`: `detect() -> str` returns `claude_code` if env `CLAUDECODE` is set, `cursor` if any env var
   starting with `CURSOR_` is set, and otherwise `unknown` (`cli` and `api` are only ever set explicitly through
   `GTJOB_HOST`, which `cvtlib.state.current_host` checks first). `init --host` overrides it. Document the detection as
   best-effort in the module docstring.
3. `status [RUN] [--all]`:
   - Prints the run slug, stage, status, checkpoints, the pending kind and its questions, artifacts
     (name, path, and a stale flag), the last 3 errors, and `next_action`.
   - Pending questions are listed from `questions.json` (id, prompt, and the default description),
     without the full rendering, which is WP-15's `cvt questions`.
   - `--all` lists every run, newest first: slug, stage, status, updated_at.
   - `--json`: `data = {state, pending_questions: [{id, prompt, default}], runs?}`.
   - Exit 4 with the hint `cvt init ...` when no run exists.
4. Tests:
   - `init` with each JD source kind (file, `--jd-text`, stdin, url).
   - Slug collisions.
   - Exit codes 2 and 5.
   - `status` on a fresh run, on a run whose `questions.json` has pending questions (write a small fixture by
     hand in the test), `--all`, and `latest` resolution.
   - The JSON envelope shape.

## Token-efficiency requirements (interfaces.md section 14)

- `status` human output is at most 8 lines:
  - slug, stage, and status
  - pending summary (counts; the first 3 question prompts truncated at 80 characters)
  - stale artifacts (names only)
  - the last error (one line)
  - `next_action`
  - a token line `tokens: ~N packet est. / N in, N out (api)` from `usage.usage_totals` (WP-01) when
    `usage.jsonl` exists
- `--json` returns the same as data; never the whole `state.json` unless `--all`.
- `init` prints 3 lines: slug, run dir, and `next_action`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_run_commands.py
REPO=$(git rev-parse --show-toplevel); CVT="$REPO/.claude/skills/tailoring-cvs/scripts/cvt.py"
cd "$(mktemp -d)" && export GTJOB_HOME=$PWD && printf 'Jane Doe\njane@example.com\n' > cv.txt \
  && uv run "$CVT" init --cv cv.txt --jd-text "Platform Engineer at Acme. Must have Kubernetes." --slug smoke \
  && uv run "$CVT" --json status latest; cd "$REPO"   # stage "initialized", next_action mentions "ingest"
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-08.md` under `## ESCALATION`. Do not change it.
