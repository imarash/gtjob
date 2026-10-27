# WP-FIX-4-5: output token caps (`max_tokens`) for the sample CV's stages

Status: the owned-file changes are done and the three named acceptance groups pass. The `tests/unit tests/integration` command fails on 2 tests in files this WP does not own and that do not read budgets (see Open issues).

## Summary

- Raised `stages.<stage>.output` in `budgets.json` to the brief's values: profile 8000, jd 5000, match 6000, questions 3000, answer_parse 2000, tailor 8000, change_request 2000, fix 1500 (unchanged), critic 3000. Input budgets are unchanged.
- `test_budgets_file_matches_the_contract` already pinned the new output values when I started, so it needed no edit.
- Added module-level constants `CONSERVATIVE_CHARS_PER_TOKEN = 3.0` and `OUTPUT_HEADROOM = 1.5`, a helper that compact-dumps each golden JSON (blanking `quote` keys in `match.json`), and two tests:
  - `test_output_caps_have_headroom_for_golden_outputs` (junior fixtures, always runs).
  - `test_output_caps_have_headroom_for_private_sample_outputs` (`pytest.skip` when `tests/fixtures/private/sample/` is absent; it is present here, so it ran and did not skip).
- Asserts only lengths; no private content is printed or asserted.

## Files changed

- `.claude/skills/tailoring-cvs/assets/budgets.json` (only `stages.*.output` values)
- `tests/unit/test_briefs.py` (added `import math`, appended the constants, helpers and 2 tests)
- `plan/reports/WP-FIX-4-5.md` (this file)

## Acceptance commands

Run with `UV_CACHE_DIR=.cache/uv uv run --no-sync ...`. Plain `uv run` tried to re-sync `.venv` and failed on a file outside the workspace (`bin/gtjob`, Operation not permitted), so `--no-sync` was used. The environment was already synced.

1. `uv run pytest -q tests/unit/test_briefs.py tests/unit/test_gtjob_stages.py tests/unit/test_gtjob_llm.py` → PASS
   - Log: `.cache/logs/WP-FIX-4-5/ac1.log`
   - Last lines:
     ```
     ........................................................................ [ 51%]
     .....................................................................    [100%]
     141 passed, 1 deselected in 4.77s
     ```
   - Focused check (`-k "budgets or headroom"`): 3 passed, 0 skipped. Log: `.cache/logs/WP-FIX-4-5/briefs-focus.log`.

2. `uv run pytest -q tests/unit tests/integration` → FAIL (2 failed, 1212 passed, 1 deselected)
   - Log: `.cache/logs/WP-FIX-4-5/ac2.log`
   - Last lines:
     ```
     FAILED tests/unit/test_render.py::test_markdown_has_sections_and_bullets - As...
     FAILED tests/unit/test_validate.py::test_layout_orphan_heading_names_the_page
     2 failed, 1212 passed, 1 deselected in 72.80s
     ```

3. `uv run pytest -q evals -m "not live"` → PASS
   - Log: `.cache/logs/WP-FIX-4-5/ac3.log`
   - Last line: `36 passed, 13 deselected in 2.71s`

## Deviations

- `test_budgets_file_matches_the_contract` was already at the new values; no edit was needed.
- `--no-sync` on every `uv run` (see above).

## Open issues

- The 2 failures in `tests/unit tests/integration` are not caused by this change:
  - `tests/unit/test_render.py::test_markdown_has_sections_and_bullets`: the markdown output lacks `## Experience`.
  - `tests/unit/test_validate.py::test_layout_orphan_heading_names_the_page`: the layout gate returns `pass` where `warn` is expected.
  - Neither test touches budgets. `render.py` and `validate.py` do not reference `budgets` or import `briefs`. Both source files and both test files are tracked and unmodified in git, so the failures likely predate this WP. I did not confirm that by reverting, because git state changes are off limits. The owning WP should look at them.
- The gate reviewer should check the 2 failures above before accepting the `tests/unit tests/integration` command.
