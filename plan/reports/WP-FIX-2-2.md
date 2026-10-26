# WP-FIX-2-2: sample PII out of committed tests

## Summary
Literal values from the real sample CV were removed from three tracked test files. They now come from the git-ignored
`tests/fixtures/private/sample-ingest.json`. Sample tests skip with a clear reason when that file is absent and run
(not skipped) when it is present.

## Files changed
- `tests/fixtures/private/sample-ingest.json` (new, git-ignored): `email`, `current_employer`, `required_text`,
  `pii_literals` (union plus surname and email domain).
- `tests/unit/test_ingest.py`: added module constant `SAMPLE_PRIVATE_FILE`. `test_real_sample_cv` loads the file
  (skips if absent) and uses its `email` and `current_employer` for the email-count and employer/date-line checks.
  All other assertions are unchanged.
- `tests/integration/test_wave2.py`: deleted `SAMPLE_REQUIRED_TEXT`, added constant `SAMPLE_PRIVATE_FILE`.
  `test_sample_cv_ingest` loads `required_text` from the file (skips if absent). Page-number, header-dedup, and glyph
  assertions are kept.
- `tests/unit/test_render.py`: earlier-experience item replaced with invented data (Pinecrest Hosting, Systems
  Administrator, 2010-03 to 2010-11); expected line is now `Pinecrest Hosting — Systems Administrator (2010)`.

## Acceptance (logs in `.cache/logs/WP-FIX-2-2/`)
1. `uv run pytest -q tests/unit/test_ingest.py tests/unit/test_render.py tests/integration/test_wave2.py` -> `57 passed in 8.77s` (a1.log)
2. `uv run pytest -q tests/unit/test_ingest.py -m sample` -> `1 passed, 18 deselected in 0.40s` (a2.log). `test_sample_cv_ingest` also passes, not skipped.
3. `git check-ignore -q tests/fixtures/private/sample-ingest.json` -> `private file ignored`
4. PII `git grep` on the three owned files -> exit 1, `no sample PII in owned files`
5. `uv run pytest -q tests/unit tests/integration` -> `575 passed, 1 skipped in 27.26s` (a5.log). The skip is `test_profile.py:440`, waiting for WP-20.

## Deviations
None.

## Open issues
Informational grep hits in other tracked files (`file:count`, files not edited, values not shown):
- `.claude/skills/tailoring-cvs/assets/schemas/profile-map.schema.json:1`
- `.claude/skills/tailoring-cvs/assets/schemas/profile.schema.json:1`
- `.claude/skills/tailoring-cvs/assets/schemas/render-model.schema.json:1`
- `tests/conftest.py:1`
- `tests/fixtures/render/senior-render.json:1`
- `tests/unit/test_refs_stages_a.py:1`
- `tests/unit/test_refs_stages_b.py:1`
- `tests/unit/test_refs_writing.py:1`

The `conftest.py` and `test_refs_*` hits are expected from wave 1 (sample path and PII-marker lists). The
three schema files and `tests/fixtures/render/senior-render.json` are not in the expected list, so the gate reviewer
should check them. They are probably an example or placeholder email domain or a similar short literal such as the
surname, not real CV text.
