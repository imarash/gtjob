# WP-19: Match report (`report`) and `critique-save`

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-01; reads artifacts defined by contracts (no code imports beyond `cvtlib` core, `profile`, `attestations`) | Sonnet (`cv-builder`) | M |

## Goal

Produce `report.md`, the honest companion to the CV. It covers requirement coverage, the confirmed facts used,
remaining gaps and how to address them honestly, source issues to confirm, `[[CONFIRM]]` items, recruiter asks,
interview talking points, and what was omitted. Also save critic output safely.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 3 (`report`, `critique-save` rows), section 6 (`reported`), `match.schema.json`,
  `jd.schema.json`, `tailored.schema.json`, `validation.schema.json`, `critique.schema.json`,
  `attestations.schema.json`, and `answers.schema.json`.
- The report must work from artifacts alone, whatever host produced them. Missing optional artifacts (critique,
  validation) produce a "not run" line, not an error.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/report.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/report.py` (`report`, `critique-save`)
- `tests/unit/test_report.py`
- `plan/reports/WP-19.md`

## Steps

1. `build_report(run_dir)` returns Markdown with these sections, in order:
   1. Header: target title (company or "unnamed company"), run slug, date, template, page count, final PDF path,
      draft flag.
   2. `## Coverage`: a table of requirement, kind, weight, strength, evidence refs (with short quotes), and a
      found-in-PDF check (from `validation.coverage.by_requirement`). Then a must-have coverage percentage.
   3. `## Confirmed facts used`: the attestations cited in tailored, with claim, type, scope labels, the user's
      verbatim words, status, and run.
   4. `## Remaining gaps`: partial/none requirements not covered by attestations, each with `match.advice`. Gaps the
      user did not confirm (unmentioned or rejected) are listed once here, with "not added, as you didn't confirm
      it".
   5. `## Source issues to confirm`: profile `source_issues` not resolved by a correction attestation.
   6. `## Items to confirm`: `[[CONFIRM: ...]]` placeholders and `open_items`.
   7. `## Recruiter asks`: `jd.recruiter_asks`, with a note that these are answered separately and never appear in
      the CV.
   8. `## Interview talking points`: `tailored.talking_points`, with refs.
   9. `## What was left out`: `tailored.omitted` and fit `dropped_ids`, with reasons.
   10. `## Defaults applied`: auto mode and skipped questions.
   11. `## Validation`: the gate table.
   12. `## Critique`: if present, the scores and top issues.
   13. `## Prompt-injection notice`: only if `jd.injection_flags` is non-empty.
2. `cvt report RUN` writes `report.md`, records it, and sets the stage to `reported` (when the stage is ≥
   `validated`, else it writes the report anyway with a "draft report" banner and leaves the stage).
   `cvt critique-save RUN FILE` extracts the first fenced JSON block if the file is Markdown, validates it against
   `critique.schema.json`, checks `tailored_version`, and saves `critique.json`.
3. Tests:
   - Build a full run directory from the junior goldens plus synthetic `validation.json` and `critique.json`. All
     sections are present.
   - Recruiter asks appear only in the report section; logistics strings do not appear elsewhere.
   - An injection notice appears for a jd with flags.
   - Missing optional artifacts are handled.
   - `critique-save` parses a Markdown-wrapped critique and rejects an invalid one with exit 1.

## Token-efficiency requirements (interfaces.md section 14)

- `report.md` ends with `## Token usage`, built from `usage.usage_totals` (WP-01). The table has these columns:
  stage, kind, model, est/actual input, cache read, output. Add a total line, and the seed run if any.
- With no `usage.jsonl`, the section says "not recorded".
- `cvt report` prints ≤ 10 lines: paths, the gate summary, and the token total. Never the report body.
- `critique-save` prints one line per criterion at most.
- Test: the junior golden with a synthetic `usage.jsonl` renders the section and totals correctly.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_report.py   # passes
```

## Definition of done

The common definition of done. The report includes the generated `report.md` for the junior fixture.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-19.md` under `## ESCALATION`. Do not change it.
