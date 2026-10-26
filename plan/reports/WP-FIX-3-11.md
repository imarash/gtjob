# WP-FIX-3-11: number scale suffixes (trillion, bn/mn/tn/T, lakh/crore)

Status: DONE (one small deviation, see below)

## Summary

- `trillion`, `bn`, `bln`, `mn`, `mln`, `tn`, `lakh`, `crore` added to `NUMBER_WORD_MULTIPLIERS` and `SCALE_WORDS`.
- `MULTIPLIERS` gained `t`, `bn`, `mn`, `tn`. `_NUMBER_RE` suffix group is now `(?i:bn|mn|tn|[kmbt])`, followed by the same `(?![A-Za-z0-9])` lookahead. Fallback to bare digits is unchanged ("5TB", "200ms", "5mm" still give the bare digits).
- `numbers()` docstring examples updated (`2bn`, `a trillion`).
- Four invented sentences from re-gate 3 are now flagged `unsupported_number`. The fifth (`crore`) is flagged too.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py` (also holds uncommitted WP-FIX-3-9 changes from before this WP)
- `tests/unit/test_lexicon.py` (also holds uncommitted WP-FIX-3-9 changes from before this WP)
- `plan/reports/WP-FIX-3-11.md`

## Acceptance

Command 1: `uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py`
Log: `.cache/logs/WP-FIX-3-11/ac1.log`
```
........................................................................ [ 91%]
.....................                                                    [100%]
237 passed in 10.90s
```

Command 2: `uv run pytest -q tests/unit tests/integration`
Log: `.cache/logs/WP-FIX-3-11/ac2.log`
```
...............................................................          [100%]
1070 passed, 1 skipped in 60.98s (0:01:00)
```
The 1 skip is pre-existing and unrelated (absent sample CV or private fixture, per `_COMMON.md` section 5).

Command 3: end-to-end provenance check (heredoc from the brief, `PYTHONPATH=.claude/skills/tailoring-cvs/scripts`)
Log: `.cache/logs/WP-FIX-3-11/ac3.log`
```
' Processed 2bn events.' ['unsupported_number']
' Processed $2mn in spend.' ['unsupported_number']
' Trained on 2T tokens.' ['unsupported_number']
' Processed a trillion events.' ['unsupported_number']
' Served 2 crore users.' ['unsupported_number']
```

Baseline before changes (same focused command): 204 passed.

## Tests added

In the existing `test_numbers_normalization` parametrize list, all values from the brief's step 4:
- New values: `a trillion requests`, `two trillion`, `2bn events`, `1.2bn`, `$3mn`, `1tn`, `1T tokens`, `2 bn`, `2 mln`, `3 bln`, `10 lakh users`, `2 crore`.
- Unchanged: `trillions of rows`, `5TB`, `200ms`, `3x faster`, `k8s`, `S3`, `5B`, `1.5k`, `5k+ hosts`, `5mm`, `Minneapolis, MN`, `Nashville, TN 37201`, `a million users`, `two billion five hundred million`.
- Extra: `Processed 2bn events.`, `Trained on 2T tokens.`, `Processed a trillion events.`, and the regression cases below.

## Deviations

- **Article rule kept off abbreviations.** Following the brief literally made `a TN town` → `1000000000000` and `a MN office` → `1000000`, because the article path (`a`/`an`/`one` before a scale word) now also accepts the abbreviations. That would make a truthful CV sentence fail provenance. I added `ABBREVIATED_SCALE_WORDS` (`bn`, `bln`, `mn`, `mln`, `tn`) and excluded them from the article path only. They still count with a digit before them ("2 bn", "2 mn"). Regression tests: `Moved to a TN town.` → `[]`, `Relocated from a MN office.` → `[]`, `a crore` → `10000000`, `a lakh` → `100000`. This is a small parser change beyond the brief's "regex only" expectation.
- `lexicon.py` and `test_lexicon.py` already had uncommitted WP-FIX-3-9 edits when this WP started. This WP only touched the lines described above.

## Open issues

- Lowercase glued `t` now scales too (`5t` → `5000000000000`). The brief asked for this. A lowercase `t` after a number is rare in CVs, but it is the one new glued suffix that is a common English-adjacent letter. Reviewers may want to watch for false positives.
- No ESCALATION: no contract or golden fixture failed.
