# WP-FIX-4-4 report: initial-batch question cap

Status: DONE. The orchestrator extended ownership to one test, `tests/integration/test_wave4.py::test_pending_question_limit_is_per_round`, and I rewrote it to the new rule.

## Summary

- `cvtlib/questions.py::_rules` groups pending checkpoint-1 questions:
  - Initial batch (empty `parent_id`, any `round`): at most `MAX_CP1_QUESTIONS` (8) in total. Message: `N pending checkpoint-1 questions in the initial batch; the limit is 8`.
  - Follow-ups (non-empty `parent_id`): at most 8 per round. Message: `N pending checkpoint-1 questions in round R follow-ups; the limit is 8`.
  - Violation code (`CODE_SCHEMA`, item `questions`) and message shape are unchanged.
- `tests/unit/test_questions.py`: three new tests (8+6 initial cap, the WP-I4 follow-up case, 9 follow-ups in one round).
- `tests/integration/test_wave4.py::test_pending_question_limit_is_per_round` rewritten. It now checks:
  - 8 initial + 1 follow-up is allowed (WP-I4 case).
  - 8 initial + 9 round-2 follow-ups gives one `round 2 follow-ups` violation.
  - 8 initial + 8 round-2 follow-ups + 8 round-3 follow-ups is allowed (each follow-up round has its own cap).
  - 8 round-1 + 1 round-2 initial question (empty `parent_id`) gives one `initial batch` violation.
  - The `_pending` helper and other wave4 tests are unchanged.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py` (cap block in `_rules` only)
- `tests/unit/test_questions.py` (three new tests)
- `tests/integration/test_wave4.py` (only `test_pending_question_limit_is_per_round`)
- `plan/reports/WP-FIX-4-4.md`

## Acceptance

1. `uv run pytest -q tests/unit/test_questions.py tests/integration/test_wave4.py`: PASS (45 passed, 0 failed)
   - Log: `.cache/logs/WP-FIX-4-4/accept1b.log`
2. `uv run pytest -q tests/unit tests/integration`: PASS (1212 passed, 0 failed, 1 deselected)
   - Log: `.cache/logs/WP-FIX-4-4/accept2b.log`
3. `uv run pytest -q tests/unit` (required by `_COMMON.md` section 7): PASS (1122 passed, 0 failed, 1 deselected)
   - Log: `.cache/logs/WP-FIX-4-4/unit.log`

Commands were run as `UV_CACHE_DIR=.cache/uv uv run --no-sync pytest ...`.

## Deviations

- Plain `uv run pytest` tried to re-sync `.venv` and failed with `Operation not permitted` on `.venv/bin/gtjob`. I used `uv run --no-sync` instead. No files were changed by the failed attempt.
- The test rewrite goes beyond a one-line fix. The brief's regression intent (follow-up rounds get their own cap) is kept, and the test now also covers the new initial-batch rule.

## ESCALATION

None. The earlier escalation is resolved by the ownership extension.

## Open issues

- None.
