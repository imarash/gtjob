# WP-FIX-4-6 report: "Recent Experience" title

## Summary

The experience section now renders as "Recent Experience" (user's uncommitted `render.py` change, kept as-is).
Two unit tests failed because they still expected the old title. `validate._layout_gate` already compares orphan
headings against the render model's section titles (casefolded), so it needed no change. The stale part was the
test's fake page text. That text now comes from the model, so the test and the validator cannot drift apart.
No docs named the rendered heading, so no doc edits were needed.

Option chosen: **test text only** (validator unchanged, docs unchanged).

## Files changed

- `tests/unit/test_render.py`: markdown assertion `## Experience` → `## Recent Experience`.
- `tests/unit/test_validate.py`: `test_layout_orphan_heading_names_the_page` derives the heading from
  `model["sections"]` (the section with `kind == "experience"`, upper-cased) instead of hard-coding "EXPERIENCE",
  and builds the expected message from the same value.

Not changed: `validate.py` (no change needed), `render.py` (forbidden), docs (no matches for the rendered heading).

## Acceptance

Command 1: `uv run --no-sync pytest -q tests/unit/test_render.py tests/unit/test_validate.py`
Result: 54 passed in 1.76s. Log: `.cache/logs/WP-FIX-4-6/acc1.log`

```
......................................................   [100%]
54 passed in 1.76s
```

Baseline before the fix (same command): 2 failed, 52 passed. Log: `.cache/logs/WP-FIX-4-6/baseline.log`.

Command 2: `uv run --no-sync pytest -q tests/unit tests/integration`
Result: 1214 passed, 1 deselected in 72.22s. Log: `.cache/logs/WP-FIX-4-6/acc2.log`

```
........................................................................ [ 94%]
..............................................................           [100%]
1214 passed, 1 deselected in 72.22s (0:01:12)
```

## Deviations

- None from the brief's required outcomes. The brief's preferred fix was in the test's fake page text, and that is what changed.

## Open issues

- None.

## ESCALATION

None.
