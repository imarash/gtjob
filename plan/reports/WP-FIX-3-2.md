# WP-FIX-3-2: spelled-out numbers count as numbers

Status: DONE (one acceptance-text deviation, see below).

## Summary
`lexicon.numbers()` now normalizes cardinal number words, so provenance rule 5 catches invented numbers written as
words. Both output and source text go through the same function.
- Words: `two`..`nineteen`, tens `twenty`..`ninety`, compounds (`twenty-five`, `twenty five`, `TWENTY-ONE`),
  `dozen` (12; `two dozen` = 24), multipliers `hundred`/`thousand`/`million` on a preceding word or digit
  (`two hundred` = 200, `5 thousand` = 5000, `two hundred and fifty` = 250). Case-insensitive, whole words.
- Excluded: `one` (alone), `a`, `an`, bare `hundred`, `hundreds`. `one` counts only as the unit of a compound.
  The exclusion is the constant `COMPOUND_ONLY_WORD` with a comment.
- Output format, signature, order and dedupe are unchanged. Digit behaviour is unchanged (`S3`, `k8s`, `Q3` -> `[]`).
- Tables are module-level constants (`NUMBER_WORD_UNITS/TENS/MULTIPLIERS`); parsing is in `_atoms`/`_parse_run`.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py` (16 new cases in `test_numbers_normalization`)
- `plan/reports/WP-FIX-3-2.md`

## Acceptance
`uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py`
(log `.cache/logs/WP-FIX-3-2/a1.log`)
```
141 passed in 0.86s
```
`uv run pytest -q tests/unit tests/integration` (log `.cache/logs/WP-FIX-3-2/a2.log`)
```
978 passed, 1 skipped in 62.38s (0:01:02)
```
No golden or fixture failed, so no `## ESCALATION`.

## Manual check (golden/junior plan, `.cache/logs/WP-FIX-3-2/manual.py`, output in `manual.log`)
I appended text to `summary.text`, ran `assemble.assemble(...)`, then `provenance.check_tailored(...)` on the result:
```
' Five years of AWS experience.'      []
' Seven years of AWS experience.'     [unsupported_number: summary t-sum mentions number '7'; not found in refs [sum-1, ...]]
' Built pipelines for twenty services.' [unsupported_number: ... number '20'; not found in refs [sum-1, ...]]
```
`numbers("Five years of AWS experience.")` now returns `["5"]`, but the "Five years" case still passes on the golden
junior fixture, and only because `exp-1` genuinely contains the digit 5 ("wrote 5 runbooks", "saving roughly 5 hours
per week"). Rule 5 is a set-membership check (number appears anywhere in the refs' text), not a check of what the
number counts. Spelled-out numbers are now treated exactly like digits, so a digit "5 years" would have passed too.

## Deviations
- The brief expects `unsupported_number` for `5` on the golden fixture. That cannot happen without changing rule 5 (a
  contract change, out of scope). I demonstrated the fix with `7` and `20`, which the fixture does not contain.
  The "twenty services" gate case is caught (`20` vs. source `12`).

## Open issues
- Rule 5 does not bind a number to its noun or unit ("5 years" is backed by "5 runbooks"). Closing that gap needs a
  contract change in interfaces.md section 8 (for example, compare number plus following unit word).
- `answers.py` keeps its own `_numbers` (out of scope), so it still sees digits only.
