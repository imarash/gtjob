# WP-FIX-3-10 report: correction exact values

## Summary
- `_correction_term_violations` now checks every word of a correction's `new_value` (`[A-Za-z][A-Za-z0-9+#]*`) with
  `lexicon.supports(word, grounding)`. It skips only `CORRECTION_FUNCTION_WORDS` (a, an, the, of, and, or, for, to, in,
  at, on, with, by, as, from). Each distinct ungrounded word gets one `unsupported_term` violation at
  `items[i].attestations[j].correction.new_value`. Common words and lowercase names are no longer exempt. The number
  check is unchanged.
- New `_current_value(profile, item_id, field)` (via `profile.iter_items`; missing or `None` counts as ""). In
  `_proposal_violations`, a `comparable` mismatch between `old_value` and the profile value gives `fact_mismatch`:
  "correction.old_value '<given>' does not match the profile's <item>.<field> '<current>'". `_proposal_violations` takes a
  new last parameter `profile` (private function, only caller updated).
- New `_plan_correction` sets the plan entry's and the resolved proposal's `correction.old_value` to the real profile
  value. `plan_table` therefore prints the real "before" value, with the clipping and ≤ 15 line cap unchanged.
  The committed attestation also carries the real old value (it is `comparable`-equal to the given one).

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py` (appended WP-FIX-3-10 tests; no existing test edited)
- `plan/reports/WP-FIX-3-10.md`

## `plan_round` outcomes (make_run profile, raw "I started at Quillmark in 2022-06, the CV is wrong" unless noted)
| Case | Outcome |
| --- | --- |
| exp-1.position → "Principal Architect" | `unsupported_term` ('Principal', 'Architect') |
| exp-1.position → "Head of Engineering" | `unsupported_term` ('Head', 'Engineering') |
| sum-1.text → "Led the company-wide platform migration and managed the team" | `unsupported_term` ('Led', 'company', 'wide', 'platform', …) |
| sum-1.text → "led the cloud migration for walmart" | `unsupported_term` ('led', 'cloud', 'migration', 'walmart') |
| exp-1.start_date old "" → 2022-06 | `fact_mismatch` (… does not match the profile's exp-1.start_date '2023-01') |
| exp-1.start_date old "1999-01" → 2022-06 | `fact_mismatch` (same message) |
| exp-1.start_date old "2023-01" → 2022-06 | passes: `… exp-1.start_date: 2023-01 -> 2022-06` |
| raw "my title at Quillmark was Principal Architect", position, old "Platform Engineer" | passes: `exp-1.position: Platform Engineer -> Principal Architect` |
| raw "the summary should say I led the platform migration", sum-1 text, real old value | passes: `sum-1.text: Synthetic platform engineer used only for tests. -> Led the platform migration` |

`round-correction.json` passes, and its line contains `exp-1.start_date: 2023-01 -> 2022-06`.

## Acceptance commands
```
$ uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py
96 passed in 11.74s            (log: .cache/logs/WP-FIX-3-10/a.log)
$ uv run pytest -q tests/integration/test_wave3.py
8 passed in 14.22s             (log: .cache/logs/WP-FIX-3-10/b.log)
$ uv run pytest -q tests/unit tests/integration
1037 passed, 1 skipped in 61.26s   (log: .cache/logs/WP-FIX-3-10/c.log)
```
3/3 pass.

## Deviations
- None. No existing test or fixture needed changing. A dry run now shows the profile's value rather than the given
  `old_value`; the two differ only in whitespace, case or Unicode normalisation, because anything else fails
  `fact_mismatch`.

## Open issues
- Words are matched as whole tokens, so a hyphenated value ("company-wide") needs both "company" and "wide" grounded.
  This is stricter than before, as the brief intends.
- The "current value" comes from the merged view (active corrections applied). A later correction of an already
  corrected field must therefore quote the corrected value as `old_value`.
