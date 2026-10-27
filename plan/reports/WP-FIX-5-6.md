# WP-FIX-5-6 report: "twice", "thrice", and 5-10x multiplier verbs

Status: DONE. Acceptance: 2 of 2 pass.

## Summary

- Added `twice` (2), `thrice` (3), `quintupled|quintupling|quintuples` (5), `sextupled|sextupling|sextuples` (6), and `decupled|decupling` (10) to `lexicon.SOLO_VALUE_WORDS`. Multi-word "order of magnitude" and `x3` were not added, per the brief.
- Updated the `numbers()` docstring with the new forms.
- Added the three suffixes from the brief to `test_invented_multiplier_words_are_unsupported_numbers`.
- Added `numbers()` cases for "twice daily", "deploying thrice as often", "quintupling throughput", "sextupled the queue depth", and "decupling batch size".
- Added `test_twice_is_supported_by_matching_source_number`: "twice a week" passes when the source says "two times a week", and fails when it says "once a week".

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py` (`SOLO_VALUE_WORDS` and the `numbers()` docstring only)
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-5-6.md`

## Acceptance

### `uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py`: PASS (218 passed)

```
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
..                                                                       [100%]
218 passed in 0.57s
```

Log: `.cache/logs/WP-FIX-5-6/focused.log`

### `uv run pytest -q tests`: PASS (1343 passed, 1 deselected, 0 skipped, 0 xfailed)

```
...............................................                          [100%]
1343 passed, 1 deselected in 139.72s (0:02:19)
```

The deselected test is marked `live` (needs network or API key). `pyproject.toml` `addopts = ["-m", "not live"]` excludes it, so it is not a skip. The e2e golden checks are part of this run, and none of the kept golden bullets fail.

Log: `.cache/logs/WP-FIX-5-6/full-tests.log`

Commands were run with `uv run --no-sync`, as the brief allows for the sandbox.

## Deviations

- None to the contract. Verification was done with `uv run pytest -q tests` rather than the brief's `tests/unit` plus e2e split. This is a superset of both.

## Open issues

- None.

## ESCALATION

- None.
