# WP-FIX-3-9: "billion" counts as a number word

## Summary

`billion` is now a scale word in the lexicon, alongside `thousand` and `million`. The change is data only: `_parse_run`
treats every `SCALE_WORDS` entry the same way, so no parser change was needed. Digits (`5B`) were already handled and are
unchanged. Plural `billions` still yields nothing, as `millions` does.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`: added `"billion": 1_000_000_000` to `NUMBER_WORD_MULTIPLIERS`
  and `"billion"` to `SCALE_WORDS`.
- `tests/unit/test_lexicon.py`: added cases for `a billion events`, `Processed a billion events.`, `one billion events`,
  `two billion events`, `5 billion`, `1.5 billion`, `two billion five hundred million`, and `billions of events` (expects `[]`).

## Acceptance

1. `uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py`
   - Log: `.cache/logs/WP-FIX-3-9/acc1.log`
   - Result: `204 passed in 10.23s`, exit 0

2. `uv run pytest -q tests/unit tests/integration`
   - Log: `.cache/logs/WP-FIX-3-9/acc2.log`
   - Result: `1027 passed, 1 skipped in 61.68s`, exit 0

## Gate sentences (`lexicon.numbers(...)`)

Log: `.cache/logs/WP-FIX-3-9/gate_sentences.log`

```
'Processed a billion events.' ['1000000000']
'Processed two billion events.' ['2000000000']
```

Before the fix, the first returned `[]` and the second returned `["2"]`. The second now returns `2000000000`, so it will
no longer pass just because the golden sources contain a `2`. It needs a source that actually states two billion.

## Deviations

- The brief's `tests/unit/test_provenance.py`, `test_assemble.py` and `test_checks.py` were included in acceptance but not
  edited, as the brief specified. The end-to-end check of the two gate sentences through `assemble` plus
  `provenance.check_tailored` on the junior golden plan was not run, because the golden plan is not part of the acceptance
  commands. Only `numbers()` output is shown above.

## ESCALATION

None. No golden or fixture failed after the change.

## Open issues

- The end-to-end re-check of the junior golden sentences through `assemble` and `provenance.check_tailored` is still
  pending. It should be confirmed at the wave gate (the expected result is that "two billion events" is now flagged).
