# WP-FIX-5-2: suppressed gap choice also removed from the question prompt

## Summary
`questions.suppress` now rewrites the prompt of a gap question that keeps some choices but drops others:
1. each dropped label is removed whole-word, case-insensitively, with one adjacent separator (`; `, `, `, ` and `, ` or `;
   trailing separator tried first, then leading); doubled separators and spaces are tidied;
2. if a dropped label or any of its `choice_terms` is still named in the prompt, the prompt is replaced by the module constant
   `GAP_PROMPT_REWRITE`, listing only the kept labels joined by `"; "` (`LABEL_SEPARATOR`).
Fully suppressed questions and non-gap questions keep their prompts. Idempotent (a second run drops nothing, so nothing changes).
New private helpers: `_word_re`, `_remove_label`, `_tidy_prompt`, `_rewrite_gap_prompt`. New constants: `LIST_SEPARATORS`,
`LABEL_SEPARATOR`, `GAP_PROMPT_REWRITE`.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`
- `tests/unit/test_questions.py` (3 new tests: label removal from the real-shaped prompt, template fallback, idempotence/no-op)
- `tests/e2e/test_sample_canonical.py` (removed only the strict `xfail` decorator)

## Acceptance
`uv run pytest -q tests/unit/test_questions.py` -> `36 passed in 3.38s` (log `.cache/logs/WP-FIX-5-2/q.log`)

`uv run pytest -q tests/e2e/test_sample_canonical.py -rx` -> `5 passed in 13.15s`, no xfail left
(log `.cache/logs/WP-FIX-5-2/e2e.log`)

`uv run pytest -q tests -rs` -> `1334 passed, 1 deselected in 137.16s`, 0 skipped (log `.cache/logs/WP-FIX-5-2/all.log`)

## Deviations
None.

## Open issues
- When two adjacent dropped labels share a list ("a and b" both dropped), the second may lack a separator and the prompt
  falls back to the template. That is the intended safe behaviour.
