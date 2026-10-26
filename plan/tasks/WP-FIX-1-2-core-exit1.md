# WP-FIX-1-2: Put the exit-1 rule in the Core of answer-parsing, checkpoint-questions, and critic-rubric

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (fix-up from WP-G1) | WP-05, WP-07, WP-I1 | Sonnet (`cv-builder`) | S |

## Goal

Only the `## Core` section of a guide goes into a stage packet (interfaces.md section 13). Every stage guide's Core must
say what to do when its check exits 1. Three Cores do not:

- `answer-parsing.md`: the rule exists only in Details (`### Self-check`).
- `checkpoint-questions.md`: the rule exists only in Details (`### Self-check`).
- `critic-rubric.md`: the rule is missing entirely.

Add one short rule to each Core and a test that keeps every stage-guide Core honest.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: interfaces.md section 13, the stage table and the fix-loop paragraph:
  `sed -n '/^## 13\./,/^## 14\./p' plan/contracts/interfaces.md`. The `fix` stage covers profile-map, jd, match, and
  questions (whole file), plus tailored (edits). It does **not** cover `answers.round.json` or `critique.draft.json`.
  Those are patched in place. `MAX_FIX_ATTEMPTS = 2`.
- Current Core lengths: answer-parsing 35 lines, checkpoint-questions 33, critic-rubric 14. The limit is 60.

## Owned files

- `.claude/skills/tailoring-cvs/references/answer-parsing.md` (Core only)
- `.claude/skills/tailoring-cvs/references/checkpoint-questions.md` (Core only)
- `.claude/skills/tailoring-cvs/references/critic-rubric.md` (Core only)
- `tests/integration/test_wave1.py`
- `plan/reports/WP-FIX-1-2.md`

## Do not touch

Details and Examples sections, other references, `plan/contracts/*`, and `UNDOCUMENTED_FLAGS` in `test_wave1.py`. A
later fix-up removes that entry after a contract change.

## Steps

1. `answer-parsing.md` Core: directly after the `Check:` line, add:
   `On exit 1: patch only the listed items in answers.round.json and rerun the dry-run (at most 2 attempts), then show the violations to the user.`
2. `checkpoint-questions.md` Core: directly after the `Check:` line, add:
   `On exit 1: run `cvt brief fix <run>`, patch only the listed questions, and rerun `cvt questions <run>` (at most 2 attempts), then show the violations to the user.`
3. `critic-rubric.md` Core: directly after the `- Check:` bullet, add a bullet:
   `- On exit 1: fix only the listed fields of critique.draft.json and rerun critique-save (at most 2 attempts).`
4. Keep the wording style of each file (plain sentences, backticks for commands). Keep each Core under 60 lines.
5. `tests/integration/test_wave1.py`: add a parametrized test over `STAGE_GUIDES`. It asserts that each Core contains
   `exit 1` (case-insensitive) and also contains `brief fix` or `at most 2`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_refs_writing.py tests/unit/test_refs_stages_b.py tests/integration/test_wave1.py   # passes
uv run pytest -q tests/unit tests/integration                                                                        # passes
```
