# WP-FIX-5-6: "twice", "thrice", and the 5-10× multiplier verbs count as numbers

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5 re-gate 1) | WP-FIX-5-3 | Haiku (`cv-builder-lite`) | XS |

## Goal

WP-FIX-5-3 added `lexicon.SOLO_VALUE_WORDS`, so ", doubling release frequency" on the junior golden's first bullet is now
an `unsupported_number`. The most common English multiplier still gets through. Each of these suffixes, appended to that
bullet, gave **no** violation from `provenance.check_tailored`:

- ", twice as fast"
- ", deploying thrice as often"
- ", quintupling throughput"

Those are invented metrics (truthfulness rule 5, `interfaces.md` section 8).

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`: `SOLO_VALUE_WORDS`, `_word_kind`, and the `numbers()`
  docstring.
- Existing tests: `tests/unit/test_lexicon.py::test_invented_multiplier_words_are_unsupported_numbers` (about line 220)
  and `test_multiplier_word_is_supported_by_matching_source_number`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py` (`SOLO_VALUE_WORDS` and the `numbers()` docstring only)
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-5-6.md`

## Steps

1. Add these entries to `SOLO_VALUE_WORDS`:
   - `twice` → 2 and `thrice` → 3
   - `quintupled|quintupling|quintuples` → 5 and `sextupled|sextupling|sextuples` → 6
   - `decupled|decupling` → 10
   Do not map "order of magnitude" (multi-word) or `x3` (digits glued to letters are names by design).
2. Add the new forms to the `numbers()` docstring line about multiplier words.
3. Tests in `test_lexicon.py`:
   - Add the 3 suffixes above to the `test_invented_multiplier_words_are_unsupported_numbers` parameters.
   - `numbers("twice daily")` is `["2"]`. A bullet that says "twice a week" passes when its source says "two times a
     week".
   - Every existing `numbers()` test still passes.
4. Run the e2e suite to confirm that no golden kept-bullet now fails.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py      # passes
uv run pytest -q tests                                                         # passes, 0 skipped, 0 xfailed
```
