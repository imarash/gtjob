# WP-FIX-5-5 report: abbreviated seniority words

Status: DONE

## Summary

- `provenance.py` now has `SENIORITY_ALIASES` (`sr`, `snr` -> `senior`; `jr`, `jnr` -> `junior`). The aliases are
  part of `_SENIORITY_RE`, so "Sr." / "Snr" / "Jr." in the headline or summary are checked.
- `_check_seniority` treats a word as supported when its canonical form or any alias of it appears as a whole word in
  the sources. Dedup is on the canonical form. The message still quotes the word as written, with the rule-4 format.
- `test_provenance.py` gained 3 parametrized mutations (headline "Sr.", headline "Snr", summary "Sr.") and 3 tests:
  "Sr." supported by "Senior" in a ref, "Senior" supported by "Sr." in a ref, and "SR-IOV" not flagged when the ref
  names "SR-IOV".

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py` (seniority constants and `_check_seniority` only)
- `tests/unit/test_provenance.py`
- `plan/reports/WP-FIX-5-5.md`

## Acceptance

1. `UV_CACHE_DIR=.cache/uv uv run --no-sync pytest -q tests/unit/test_provenance.py`
   - Log: `.cache/logs/WP-FIX-5-5/provenance.log`
   - Result: `65 passed in 0.43s`, exit 0
2. `UV_CACHE_DIR=.cache/uv uv run --no-sync pytest -q tests`
   - Log: `.cache/logs/WP-FIX-5-5/all.log`
   - Result: `1349 passed, 1 deselected in 138.04s`, exit 0
   - The 1 deselected test is a `live`-marked test. `pyproject.toml` sets `addopts = ["-m", "not live"]`. It is not a
     skip or xfail, so the "0 skipped, 0 xfailed" condition holds.
3. Common check: `tests/unit` is included in the full run above (`tests` covers it), so it passes too.

## Deviations

- Acceptance used `uv run --no-sync` (the brief's fallback) for both commands, with `UV_CACHE_DIR=.cache/uv`.
- The SR-IOV test asserts no `'SR'`/`'Sr'` seniority violation, not a full `check_tailored == []`. The rest of the
  summary text is not part of this WP.

## Open issues

- None for this WP.
