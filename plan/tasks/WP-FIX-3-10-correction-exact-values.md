# WP-FIX-3-10: A correction's new value uses only the user's words, and its old value is the real profile value

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 2) | WP-FIX-3-7 | Sonnet (`cv-builder`) | S |

## Goal

WP-FIX-3-7 checks only the terms `lexicon.find_terms` returns in a correction's `new_value`. Common words are exempt,
and `find_terms` skips lowercase names. A correction's `new_value` replaces the profile field in
`profile.merged_view`, so provenance treats it as a CV fact. At re-gate 2, with `raw_text` "I started at Quillmark in
2022-06, the CV is wrong", these corrections passed `answers.plan_round` (the dry run):

- `exp-1.position` → "Principal Architect", and `exp-1.position` → "Head of Engineering". This is title promotion,
  which truthfulness rule 6 forbids.
- `sum-1.text` → "Led the company-wide platform migration and managed the team".
- `sum-1.text` → "led the cloud migration for walmart".

The agent-supplied `old_value` is also not checked. `references/answer-parsing.md` requires "an exact `old_value`",
but `old_value` "" and "1999-01" both passed for `exp-1`, whose real values are `position` "Platform Engineer" and
`start_date` "2023-01". The dry-run line showed `exp-1.position:  -> Principal Architect`, so the user never sees what
is being replaced.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: `sed -n '/^### Applying a reply/,/^### Checkpoint 2/p' plan/contracts/interfaces.md`, and
  `references/truthfulness.md` rule 6.
- `cvtlib/answers.py`: `_proposal_violations` (the `is_correction` branches), `_correction_term_violations`,
  `_grounding`, `plan_table` (the correction suffix), and the codes `CODE_VERBATIM` (`fact_mismatch`) and `CODE_TERM`.
- `cvtlib/profile.py`: `iter_items` (item objects by ID) and `comparable`. `merged_view` sets
  `target[field] = new_value`, so the current value is the item object's `field` key.
- Fixtures: `tests/fixtures/checkpoint/round-correction.json` (`exp-1.start_date` 2023-01 → 2022-06, real old value)
  must keep passing. Do not edit fixtures.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py`
- `plan/reports/WP-FIX-3-10.md`

## Steps

1. **Every word is the user's.** For a correction, split `new_value` into word tokens (letters, then letters or digits,
   for example `[A-Za-z][A-Za-z0-9+#]*`). Drop a short, named module-level set of function words (`a`, `an`, `the`,
   `of`, `and`, `or`, `for`, `to`, `in`, `at`, `on`, `with`, `by`, `as`, `from`), with a one-line comment. Each
   remaining word must satisfy `lexicon.supports(word, grounding)` (the same grounding text as now). Otherwise add an
   `unsupported_term` violation at `items[i].attestations[j].correction.new_value` that names the word. This replaces
   the `find_terms`-only check, so common words and lowercase names are no longer exempt. Keep the number check as it
   is.
2. **Exact old value.** Look up the item's current `field` value in the run's profile (a missing or `None` value
   counts as ""). If `profile.comparable(old_value)` differs from `profile.comparable(current)`, add a `fact_mismatch`
   violation: "correction.old_value '<given>' does not match the profile's <item_id>.<field> '<current>'".
3. **Dry run shows the real value.** In `plan_table`, the correction suffix prints the profile's current value as the
   "before" value. Keep the `CORRECTION_VALUE_WIDTH` clipping and the ≤ 15 line cap.
4. Tests in `test_answers.py` (run against the `make_run` profile, `nested-engagements.json`):
   - With raw_text "I started at Quillmark in 2022-06, the CV is wrong", each of these fails with `unsupported_term`
     naming the first ungrounded word: position "Principal Architect" (`Principal`), position "Head of Engineering",
     text "Led the company-wide platform migration and managed the team", and text "led the cloud migration for
     walmart" (`walmart` must be among the named words).
   - `old_value` "" or "1999-01" on `exp-1.start_date` fails with `fact_mismatch`; "2023-01" passes.
   - It passes when raw_text is "my title at Quillmark was Principal Architect" (position, old "Platform Engineer"),
     and when raw_text is "the summary should say I led the platform migration" (text "Led the platform migration",
     with the real `sum-1` text as old value).
   - `round-correction.json` passes, and its dry-run line contains `exp-1.start_date: 2023-01 -> 2022-06`.
   - Every existing test still passes, including the golden junior round, every `tests/fixtures/checkpoint/round-*.json`
     round, and the `--select` parity test. Update an existing test's inline correction only if it relied on a wrong
     `old_value`, and list the change under `## Deviations`. If a committed fixture fails, report it under
     `## ESCALATION`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py   # passes
uv run pytest -q tests/integration/test_wave3.py                           # passes
uv run pytest -q tests/unit tests/integration                              # passes
```

In the report, paste the `plan_round` outcome (violation codes, or the `+ correction` line) for each case in step 4.
