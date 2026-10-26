# WP-FIX-1-2 report

## Summary
Added the exit-1 rule to the `## Core` of `answer-parsing.md`, `checkpoint-questions.md`, and `critic-rubric.md`, using the wording from the brief. Added a parametrized test over `STAGE_GUIDES` in `tests/integration/test_wave1.py`. It asserts that each Core contains `exit 1` (case-insensitive) and also `brief fix` or `at most 2`.

## Files changed
- `.claude/skills/tailoring-cvs/references/answer-parsing.md` (Core, one line after the `Check:` block)
- `.claude/skills/tailoring-cvs/references/checkpoint-questions.md` (Core, one line after `Check:`)
- `.claude/skills/tailoring-cvs/references/critic-rubric.md` (Core, one bullet after `- Check:`)
- `tests/integration/test_wave1.py` (`test_stage_guide_core_says_what_to_do_on_exit_1`)
- `plan/reports/WP-FIX-1-2.md`

## Acceptance
```
uv run pytest -q tests/unit/test_refs_writing.py tests/unit/test_refs_stages_b.py tests/integration/test_wave1.py
99 passed in 0.19s        (log: .cache/logs/WP-FIX-1-2/a1.log)

uv run pytest -q tests/unit tests/integration
278 passed in 2.56s       (log: .cache/logs/WP-FIX-1-2/a2.log)
```

## Deviations
In `answer-parsing.md` the `Check:` statement spans two lines (the second is the `` (`cvt` = ...) `` parenthetical). The new line goes after the parenthetical so that it stays attached to the Check.

## Open issues
None. `UNDOCUMENTED_FLAGS` was left untouched, as instructed.
