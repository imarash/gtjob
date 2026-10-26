# WP-I3 report: integrate wave 3

Status: DONE. Acceptance 2/2 pass. No escalation.

## Summary

- `tests/integration/test_wave3.py` (8 tests) drives the junior run through real `cvt` subprocesses in a temp workspace,
  from `init` to `report`, with the goldens standing in for AI output: `questions.json`, `answers.round.json` (dry run
  writes nothing, then commit), `tailor-plan.json` -> `assemble`, `edits-001.json`, then `approve`, `fit` (no PNGs),
  `validate`, `report`.
- Asserts: every stage reached, `reported`, one `final/*.pdf` of 1 page, `att-001` proposed -> `active`,
  `attestations_used`, `## Token usage` in `report.md`, and `render --template classic` on the same run (1 page, marks
  `validation`, `final_pdf`, `report` stale, `validate` passes again).
- Every `cvt brief` stage (profile, jd, match, questions, answer_parse, tailor, change_request, critic) builds within its
  budget with no `budget` warning. The `fix` packet is built after a real `assemble` failure (plan ref to an unknown id).
  One `usage.jsonl` line per packet.
- Checkpoint 1 via `answers-apply --select q-1=helm --default-rest` is compared with the round replay (see Deviations).
- `questions --format host --host claude_code` splits into more than one call, at most 4 questions per call, 4 options
  per question, headers of at most 12 characters, with `(1/2)`/`(2/2)` parts. The Cursor shape has `title` and
  `questions[].{id,prompt,options}`.
- `lint-skill --all` exits 0 (in the workspace and from the repo root). `package-skill --out <tmp>` makes a zip with no
  `out/`, `profiles/`, `.cache/`, `CVs/`, or `__pycache__` entries.
- Every `$CVT <cmd>` / `cvt.py <cmd>` example in `SKILL.md` and `references/commands.md` names a registered subcommand
  (parsed from `cvt --help`), and every `--flag` in an example exists in that command's `--help`. Every registered
  command appears in `commands.md`.

## Files changed

- `tests/integration/test_wave3.py` (new)
- `tests/unit/test_validate.py` (WP-14, minimal): `junior_run` now adds the Helm attestation as `proposed`, sets stage
  `tailored`, and calls the real `approve --all` instead of setting `active` and `approved` directly.
- `.claude/skills/tailoring-cvs/references/host-notes.md` (WP-18, minimal): reworded the local `typst compile` hint to
  not name the typst `--font-path` flag. `tests/integration/test_wave1.py::test_reference_flags_exist_in_section_3`
  fails on any `--flag` not in interfaces section 3 (it passed for WP-18 only because that test was not re-run).
- `plan/reports/WP-I3.md`

No fixture mismatches: WP-29 reported none, and there is no `xfail` in the repo.

## Acceptance

```text
$ uv run pytest -q tests/unit tests/integration        (log: .cache/logs/WP-I3/suite.log)
........................................................................ [ 98%]
..............                                                           [100%]
949 passed, 1 skipped in 54.03s

$ uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all   (log: .cache/logs/WP-I3/lint.log)
lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile
exit 0
```

The skipped test is the private-sample ingest test (needs the real sample CV expectations).

## Cross-WP joins checked

- WP-14 shortcut: replaced by real `approve` (above).
- WP-12/WP-17: `render --template classic` works on a run at `rendered`.
- WP-18 docs vs CLI: all commands and example flags exist (test above).
- WP-19 report vs artifacts: `report` consumed the real `validation.json`, `fit.json`, `answers.json`, `usage.jsonl`
  written by WP-14/WP-15/WP-29. The report's token table lists the questions, tailor and critic packets.
- WP-15 host format: matches section 7. In `--json` the shape is at `data.render`.

## Deviations

- The `--select` replay cannot give a byte-identical store to the golden round: the round attests Helm at scope `items:
  exp-1`, placement `skills_and_bullets`, terms `Helm`; `--select` follows section 7 (gap choice -> skills-only global
  attestation, terms from the choice value `Helm|Helm charts`). The test asserts what is the same: final stage,
  checkpoint state, round count, question statuses (q-1 answered, q-2/q-3 defaulted), and a single proposed `att-001`
  with type `skill` and claim `Helm`. It does not compare scope, placement or terms.
- The `fix` packet is checked in its own run (an assemble failure) rather than the main run, because the main run never
  fails a check.
- `apply-edits` with `approve_all` already moves the run to `approved` (WP-16 decision), so the test's explicit
  `approve` afterwards is an idempotent re-approval. The `approve` path from `awaiting_approval` with pending items is
  covered by `test_validate.py::junior_run` (`approve --all`).

## Open issues

- `test_wave1.py`'s flag test only checks references; `SKILL.md` flags are checked only through the new test (examples
  with `$CVT` prefix). Plain-text mentions of flags outside examples are not validated.
- The compact `diff` output is longer than 15 lines (21 on the golden), a WP-16 decision (exempt from the cap).
- Gate reviewer: look first at the `--select` deviation (above) and the `host-notes.md` rewording.
