# WP-FIX-3-4: An attestation suppresses a gap choice when it covers any of the choice's synonyms

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3) | WP-15 | Haiku (`cv-builder-lite`) | S |

## Goal

Gap choice values are written as `term|synonym` (interfaces.md section 7), so the parts are alternatives.
`questions._covering` requires an attestation to cover **every** part. At the gate, after the junior run activated
`att-001` (Helm, terms `["Helm"]`), a second run on the same CV and JD still asked q-1 "a) Helm": the golden choice
value is `Helm|Helm charts`, and nothing covers "Helm charts". Suppression by existing attestations therefore fails
in the canonical case.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`
- `tests/unit/test_questions.py`
- `plan/reports/WP-FIX-3-4.md`

## Steps

1. In `questions.py`, separate the two value kinds:
   - A `term|synonym` value is covered when an active attestation covers **any** of its parts (use the existing
     `attestations.find_by_terms` per part; collect the covering attestations of the first part that hits).
   - A requirement-ID value (`req-N`) is unchanged: **every** requirement keyword must be covered.
2. Keep the suppression reason format (`answered by att-001 (Helm)`) and `data.suppressed`.
3. Tests:
   - Golden `tests/fixtures/golden/junior/questions.json` with an active attestation whose terms are `["Helm"]`
     suppresses the `helm` choice of q-1 and keeps `python_bash`.
   - A proposed (not active) attestation does not suppress.
   - A `req-N` choice whose requirement has two keywords is not suppressed when only one is covered (existing test
     keeps passing).

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_questions.py tests/unit/test_answers.py   # passes
uv run pytest -q tests/unit tests/integration                              # passes
```
