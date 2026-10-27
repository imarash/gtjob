# WP-FIX-4-4: the 8-question cap cannot be dodged by labelling initial questions as later rounds

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4) | WP-15, WP-I4 | Haiku (`cv-builder-lite`) | XS |

## Goal

`interfaces.md` section 7: the AI writes `questions.json` with at most 8 pending checkpoint-1 questions. WP-I4 made the
cap per round (`cvtlib/questions.py::_rules`), so that follow-ups added with `questions --add` before `answers-apply
--commit` do not add up with the uncommitted round 1. The gate accepts that intent. But the per-round count now lets an
AI-written initial `questions.json` hold 14 pending questions (8 labelled `round: 1` and 6 labelled `round: 2`), and
`questions.check` reports no violation.

In the schema, `round` is "1 for the initial batch; follow-ups get round+1", and follow-ups carry `parent_id`
(`answers.py` sets it on every follow-up skeleton).

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`: `_rules`, the `open_by_round` block (around line 160),
  and `MAX_CP1_QUESTIONS`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py` (only the cap block in `_rules`)
- `tests/unit/test_questions.py`
- `plan/reports/WP-FIX-4-4.md`

## Steps

1. Change the cap block to count two groups of pending checkpoint-1 questions:
   - **Initial batch:** questions with an empty `parent_id`, whatever their `round`. At most `MAX_CP1_QUESTIONS` in
     total.
   - **Follow-ups:** questions with a non-empty `parent_id`. At most `MAX_CP1_QUESTIONS` per `round`.
   Keep the violation code and the message shape (`"N pending checkpoint-1 questions …; the limit is 8"`). Name the
   group in the message ("initial batch" or "round R follow-ups"). Update the comment.
2. Tests in `test_questions.py`:
   - 8 initial questions in round 1 plus 6 initial questions (empty `parent_id`) in round 2 → one cap violation.
   - 8 pending round-1 questions plus 1 follow-up in round 2 with `parent_id: "q-1"` → no cap violation (the WP-I4 case).
   - 9 follow-ups in one round, each with a `parent_id` → one cap violation.
3. Run the full suite, including `tests/integration/test_wave4.py`, which has WP-I4's per-round regression tests.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_questions.py tests/integration/test_wave4.py   # passes
uv run pytest -q tests/unit tests/integration                                   # passes
```
