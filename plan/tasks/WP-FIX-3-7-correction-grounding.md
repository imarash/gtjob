# WP-FIX-3-7: Correction attestations must be grounded in the user's words and shown in the dry run

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 1) | WP-FIX-3-3 | Sonnet (`cv-builder`) | S |

## Goal

WP-FIX-3-3 grounds the terms of non-correction attestations, but corrections skip every word check. Once active, a
correction's `new_value` replaces the profile field in `profile.merged_view`, so provenance treats it as a CV fact.
At the re-gate, with `raw_text` "I started at Quillmark in 2022-06, the CV is wrong", these corrections passed
`answers.plan_round` (the dry run):

- `field: text` on `sum-1`, `new_value` "Led the Kubernetes migration for Walmart across ArgoCD and Istio". The merged
  view's `sum-1` then reads exactly that.
- `field: position`, `new_value` "Principal Kubernetes Architect".
- The dry-run line showed only `+ correction "fix a bullet" [correction_only] global`, so the user approves a change
  they never see.
- A correction with `terms: ["Kubernetes"]` also passed (the line showed `terms=Kubernetes`). Correction-only
  attestations do not license bullet terms, but `attestations.find_by_terms` does not filter by type, so it would
  suppress a Kubernetes gap question.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: `grep -n 'Applying a reply' plan/contracts/interfaces.md` (section 7) and section 8 ("merged view").
- `cvtlib/answers.py`: `_proposal_violations` (the `is_correction` branch and the final `if not is_correction`),
  `_term_violations`, `_grounding`, and `plan_table` (the `+ …` line). Reuse `lexicon.find_terms`,
  `lexicon.supports`, and `lexicon.common_words()`.
- Fixtures: `tests/fixtures/checkpoint/round-correction.json` (start date 2023-01 → 2022-06) must keep passing.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py`
- `plan/reports/WP-FIX-3-7.md`

## Steps

1. For a correction, every term that `lexicon.find_terms(correction.new_value)` returns, minus `common-words.txt`
   words, must satisfy `lexicon.supports(term, grounding)` (same grounding text as WP-FIX-3-3). Otherwise add an
   `unsupported_term` violation that names the term and `items[i].attestations[j].correction.new_value`. Numbers are
   already checked; keep that.
2. A correction with any non-blank entry in `terms` is a `schema` violation: "a correction carries no terms; put the
   new value in correction.new_value".
3. `plan_table`: a correction's `+ …` line appends ` <item_id>.<field>: <old_value> -> <new_value>` (truncate
   `new_value` to a named constant width, for example 60 characters, with `…`). Keep the table at ≤ 15 lines.
4. Tests in `test_answers.py`:
   - The three gate corrections above (text on a profile item, position, terms) → exit 1 with the expected codes,
     naming `Kubernetes` (and `Walmart`) for the first two.
   - The position correction passes when `raw_text` says "my title at Quillmark was Principal Kubernetes Architect".
   - `round-correction.json` still passes, and its dry-run line contains `exp-1.start_date: 2023-01 -> 2022-06`.
   - The golden junior round, every `tests/fixtures/checkpoint/round-*.json` round, and the `--select` parity test
     still pass. If a committed fixture fails, report it under `## ESCALATION`; do not edit fixtures.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py   # passes
uv run pytest -q tests/integration/test_wave3.py                           # passes
uv run pytest -q tests/unit tests/integration                              # passes
```
