# WP-I3: Integrate wave 3 (fit/validate, questions/answers, diff/edits, classic, skill entry points, report, packets/assemble)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (after WP-14…WP-19, WP-29, before G3) | WP-14…WP-19, WP-29 | Sonnet (`cv-builder`) | M |

## Goal

At the end of this WP, the skill path is complete: the junior run goes from `init` to `report` using only
`cvt` commands, with goldens standing in for AI output. The skill lints, and the package builds.

## Context

- Read `plan/tasks/_COMMON.md` and every `plan/reports/WP-1[4-9].md` (check ESCALATION sections first).
- Known joins to check:
  - WP-14's test shortcut that sets `approved` directly → use the real `approve` now.
  - WP-12's "template not installed" path → `classic` (WP-17) must render through `render --template classic`.
  - WP-18's `SKILL.md` and `references/commands.md` → every command and flag exists.
  - WP-19's report sections → consistent with the artifacts WP-14 and WP-16 actually write.
  - WP-15's `questions --format host` → the shape in section 7.
- You may make **minimal** fixes in wave 1-3 files, each listed in your report with its reason. Never edit
  `plan/contracts/*`.

## Owned files

- `tests/integration/test_wave3.py`
- Minimal fixes in wave 1-3 files (listed in your report)
- `plan/reports/WP-I3.md`

## Steps

1. First, fix any `## Fixture mismatches` that WP-29 reported in the junior goldens, and remove the `xfail`.
2. `test_wave3.py`, in a temp workspace:
   - The full junior run through real commands, replaying the golden `questions.json`, `answers.round.json` (dry
     run, then commit), `tailor-plan.json` → `assemble`, and `edits-001.json`. Then `approve`, `fit` (no PNGs),
     `validate`, and `report`. Also replay checkpoint 1 via `answers-apply --select` and assert the same store
     state as the round replay.
   - Every `cvt brief` stage builds for this run within its budget, and `report.md` has `## Token usage`. Assert `reported`, `final/*.pdf`, and that the attestations became `active`.
   - Repeat `render --template classic` on the same run.
   - `lint-skill --all` exits 0. `package-skill --out <tmp>` produces a zip without `out/` or `profiles/` entries.
   - Every `` `cvt ...` `` example in `SKILL.md` and `references/commands.md` names a registered subcommand. Parse
     `cvt --help`.
   - `questions --format host --host claude_code` respects ≤ 4 questions and ≤ 4 options per call.
3. Update WP-14's validate test to use the real `approve` (a minimal edit).
4. Run the whole suite.

## Acceptance criteria

```bash
uv run pytest -q tests/unit tests/integration                         # passes
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all    # exit 0
```

## Definition of done

The common definition of done. The report lists every cross-WP edit.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-I3.md` under `## ESCALATION`. Do not change it.
