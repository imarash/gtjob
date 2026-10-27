# WP-FIX-5-4: seniority words in the headline and summary must be supported by their refs

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5) | WP-13 | Sonnet (`cv-builder`) | S |

## Goal

Product rule: never invent titles. The style guide says the headline is "Never a job title as if held", and
`stage-tailor.md` says "Do not claim a level the evidence does not show". Only the prompt enforces this today. The WP-G5
probe on the junior golden (profile title "Junior DevOps Engineer") got **no** violation from `provenance.check_tailored`
for any of these:

- headline "Senior DevOps Engineer"
- headline "Lead DevOps Engineer · AWS"
- headline "Staff Platform Architect"
- the summary rewritten from "Junior DevOps engineer …" to "Senior …" and to "Principal DevOps architect …"

Rule 6 already catches a changed job title.

## Context

- Read `plan/tasks/_COMMON.md`.
- `interfaces.md` section 8 rules 4 and 6 and the message format:
  `sed -n '/^## 8\./,/^## 9\./p' plan/contracts/interfaces.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`: `_check_element` (the term check), `KIND_HEADLINE`,
  `KIND_SUMMARY`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`
- `tests/unit/test_provenance.py`
- `plan/reports/WP-FIX-5-4.md`

## Steps

1. Add a module constant `SENIORITY_WORDS` (casefolded): `junior`, `senior`, `staff`, `principal`, `distinguished`,
   `chief`, `head`, `director`, `vp`, `vice president`. Do not include `lead`, because it is mostly a verb in CV text. Do
   not include `executive`, because "executive stakeholders" is common and harmless.
2. In `_check_element`, for `KIND_HEADLINE` and `KIND_SUMMARY` elements only: every seniority word in the text (whole
   word, case-insensitive) must appear in the element's resolved sources (the same `source` string the term check uses).
   Otherwise, report `unsupported_term` with the exact rule-4 message format, for example
   `headline t-header mentions 'Staff'; not found in refs [basics, exp-1]`. Use the word as written in the text.
   Rule 4's code and message apply, so this needs no contract change.
3. Tests in `test_provenance.py`:
   - The 5 junior mutations above fail, except "Lead DevOps Engineer", which stays allowed by design.
   - A summary "Senior platform engineer …" whose refs include an item containing "Senior" passes.
   - The untouched junior and synthetic goldens still pass.
4. Run the e2e suite. The private sample's golden plan (headline "Platform & Site Reliability Engineering · AWS ·
   Kubernetes", summary starting "Senior platform and reliability engineer" with refs including `sum-2`, "Senior IT
   Consultant…") must still pass. If a golden fails, report it. Do not edit goldens.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_provenance.py                                 # passes
uv run pytest -q tests                                                         # passes, 0 skipped on the orchestrator machine
```
