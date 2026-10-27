# WP-FIX-4-2: wrap CV/JD-derived packet sections in `<untrusted_document>`

## Summary
- `briefs._wrap` neutralizes `<untrusted_document` / `</untrusted_document` (case-insensitive) inside the text to
  `&lt;…` (module constants `UNTRUSTED_TAG_PATTERN`, `UNTRUSTED_TAG_INERT`). Added public alias `wrap_untrusted`.
- `_inputs_for` now wraps, each with its heading line inside the wrapper:
  - match: `jd digest`, `profile digest`, `prematch`.
  - tailor: `jd digest`, `profile digest`, `match strengths`, and the seed plan JSON as `seed plan`.
  - questions: `gaps`, `source issues`, `item headers`, `role labels`.
  - answer_parse: `pending questions`, `item headers`, `role labels` (reply stays in `<user_reply>`).
  - change_request: `tailored outline`, `named items` (reply stays in `<user_reply>`).
  - critic: `tailored outline`, `jd digest`, `validation`.
  - fix: `offending items` (the label line is inside the wrapper).
  - `_run_id_line` and `_answers_summary` stay unwrapped.
- `prompts.build_prompt`: the digest block is now the wrapped digest (`briefs.wrap_untrusted(briefs.PROFILE_DIGEST_NAME, …)`).
  The whole wrapper in the inputs is replaced by `DIGEST_PLACEHOLDER`, so no empty or doubled wrapper remains.
  Cache breakpoints are unchanged. `digest.txt` on disk stays raw.
- Budgets: all packet budget tests still pass; `budgets.json` untouched.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `src/gtjob/prompts.py`
- `tests/unit/test_briefs.py` (sentinel tests for match/tailor/questions/answer_parse/change_request/critic/fix, closing-tag
  neutralization, JD requirement containing a closing tag, headings-inside-wrapper)
- `tests/unit/test_gtjob_stages.py` (sentinel property for `build_prompt` match and tailor, digest block wrapped, placeholder once)
- `plan/reports/WP-FIX-4-2.md`

## Acceptance
`uv run pytest -q tests/unit/test_briefs.py tests/unit/test_gtjob_stages.py`
```
120 passed in 2.60s
```
`uv run pytest -q tests/unit tests/integration`  (log `.cache/logs/WP-FIX-4-2/full.log`)
```
1212 passed, 1 deselected in 70.34s (0:01:10)
```
`uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all`
```
lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile
```
Sample run (`out/20261026-golden-sample`), count of `<untrusted_document name`:
```
match: 3
tailor: 3
questions: 4
```

## Deviations
- Seed: only the plan JSON is wrapped (`seed plan`); the `# Seed (run …)` heading and the "start from the seed … set
  seed_run" instruction stay outside, because the instruction is ours and must not sit inside a data wrapper.
- Tests run as `uv run --no-sync pytest …` because plain `uv run` tries to rebuild/replace `.venv/bin/gtjob`, which the
  sandbox forbids (`Operation not permitted`). Same tests, no code difference.
- Tests count opening tags as `<untrusted_document name="` since the injection rule prose mentions the bare
  `<untrusted_document>` tag.
- Extra wrapped sections beyond the brief's list: `match strengths` (model output derived from CV/JD), `validation`
  (messages quote CV text).

## Open issues
- One earlier full run reported `tests/integration/test_wave4.py::test_pending_question_limit_is_per_round` failing
  (1 failed, 1211 passed); the immediate rerun passed fully. Files such as `questions.py` and its tests were being modified
  by another worker at the same time, so this is likely concurrent-edit noise. Gate reviewer should rerun it.
- `_pending_questions`/`_source_issues` with no content are still wrapped (heading plus `-`), costing a few tokens.
