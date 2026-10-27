# WP-FIX-5-4: seniority words in headline and summary must be supported by refs

Status: DONE

## Summary
- `provenance.py`: added `SENIORITY_WORDS` (junior, senior, staff, principal, distinguished, chief, head, director, vp,
  vice president; no `lead`, no `executive`), `SENIORITY_KINDS`, and `_check_seniority`, called from `_check_element`
  for `headline` and `summary` elements only. Each level word (whole word, case-insensitive, deduplicated, reported as
  written in the text) must appear as a whole word in the joined sources of the element's refs; otherwise an
  `unsupported_term` violation uses the exact rule-4 message, e.g.
  `headline t-header mentions 'Staff'; not found in refs [basics, exp-1]`. No contract change.
- `test_provenance.py`: added tests for headline "Senior DevOps Engineer" / "Staff Platform Architect" and summary
  "Senior ..." / "Principal ..." (all fail), "Lead DevOps Engineer · AWS" (allowed), exact message and casing, a
  summary "Senior platform engineer ..." passing when a cited item contains "Senior", whole-word matching ("headed"),
  and bullets not being checked. The untouched junior golden still passes (`test_golden_passes`).

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`
- `tests/unit/test_provenance.py`
- `plan/reports/WP-FIX-5-4.md`

## Acceptance
`uv run --no-sync pytest -q tests/unit/test_provenance.py` (log: `.cache/logs/WP-FIX-5-4/`)
```
59 passed
```
`uv run --no-sync pytest -q tests/unit`
```
all passed (log: .cache/logs/WP-FIX-5-4/unit.log)
```
`uv run --no-sync pytest -q tests` (log: `.cache/logs/WP-FIX-5-4/all.log`)
```
1330 passed, 1 deselected, 1 xfailed in 138.62s (0:02:18)
```
The private-sample golden plan and e2e suite pass, so the sample's "Senior platform and reliability engineer" summary
is still accepted via `sum-2` / "Senior IT Consultant".

## Deviations
None. `uv run --no-sync` was used because plain `uv run` cannot rewrite `.venv/bin/gtjob` in the sandbox.

## Open issues
- A first full run had one failure in `tests/e2e/test_sample_canonical.py::test_answer_parse_packet_fits_budget_on_sample`
  (alongside my own test's `draft` kwarg bug, since fixed). It passed in isolation and in the next full run, so it looks
  flaky under load. The gate reviewer may want to confirm.
- `xfailed` 1 and `deselected` 1 are pre-existing; this WP did not skip any tests.
