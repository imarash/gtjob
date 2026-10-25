# WP-26: `gtjob` CLI end-to-end with a fake model (offline), and cross-host resume

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 | Waves 1-4 (WP-21, WP-22 wired by I-4) | Sonnet (`cv-builder`) | M |

## Goal

Prove that the terminal path works end to end with the real `gtjob` code. Only the network client is
replaced: `FakeClient` returns golden artifacts. Also prove that runs move freely between the IDE path (raw
`cvt` commands, as an agent would run them) and the CLI.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 12 (including the non-interactive stop), section 13, and section 6.
- Inject the fake client the way WP-21/22 expose it (`gtjob.llm.FakeClient`; a `GTJOB_FAKE_LLM=<dir>` env hook if I-4
  added one). Read `plan/reports/WP-I4.md` first for the final wiring.
- Use a temporary workspace through `GTJOB_HOME`. Never touch the real `out/` or `profiles/`.

## Owned files

- `tests/e2e/test_cli_offline.py`
- `tests/e2e/test_cross_host.py`
- `tests/e2e/fake_llm/` (canned stage responses assembled from the junior goldens, plus one deliberately bad tailor
  response)
- `plan/reports/WP-26.md`

## Steps

1. `test_cli_offline.py`:
   - `gtjob tailor --cv <junior cv> --jd <junior jd> --answers <yaml>` reaches `reported` with exit 0.
   - The tailor stage's first response mentions an unsupported tool. The fix loop retries, and the final
     plan assembles and passes `check-tailored`. The retry prompt is the `fix` packet (violations and offending
     items only).
   - `--auto` produces no attestations.
   - A second identical run hits the LLM cache: `FakeClient` call count is 0 for cached stages.
   - `gtjob status`, `gtjob render RUN --template classic`, and `gtjob profile list` work.
   - `gtjob edit RUN --text "drop the earlier experience line"` → a new version, re-rendered.
2. `test_cross_host.py`:
   - IDE → CLI: drive `cvt` commands (as an IDE agent would) up to `awaiting_answers`, then
     `gtjob continue RUN --answers <yaml>` → `reported`.
   - CLI → IDE: `gtjob tailor` with non-TTY stdin and no answers → exit 6 at checkpoint 1. Then apply the golden
     round with `cvt answers-apply --commit` and continue with raw `cvt` commands to `reported`.
   - Checkpoint 2 handoff: CLI stops at `awaiting_approval` (exit 6), then `cvt apply-edits` + `cvt approve` → the
     CLI `gtjob continue` finishes.
   - In every case, `state.history[].host` records both hosts. Run the IDE-side `cvt` subprocesses with
     `GTJOB_HOST=cursor` (or `claude_code`); `gtjob` sets `cli` itself.

## Token-efficiency requirements (interfaces.md section 14)

- Assert routing and escalation through `FakeClient`'s recorded models:
  - `jd` on Haiku.
  - After a failed `jd-check` → one Sonnet retry.
- Assert the usage table printed at the end, and that `usage.jsonl` has `kind: api` lines with synthetic usage.
- Cross-host resume: the history records `host` for each step, and the second host continues from the
  `next_action` without re-running packets for completed stages (no new `kind: packet` lines for them).

## Acceptance criteria

```bash
uv run pytest -q tests/e2e/test_cli_offline.py tests/e2e/test_cross_host.py   # passes, no network
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-26.md` under `## ESCALATION`. Do not change it.
