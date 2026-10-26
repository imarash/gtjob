# WP-I2: Integrate wave 2

Status: DONE. Stand-ins removed; integration tests pass. `tests/unit` + `tests/integration`: 573 passed, 1 skipped,
2 failed. Both failures are the known environment-sensitive WP-01 tests (see Open issues) and pass in a clean env.

## Summary
- Removed all `TODO(I-2)` stand-ins. `provenance.py` now delegates to `cvtlib.profile` (`iter_items`, `item_text`,
  `merged_view`, `normalize_text`, `comparable`) and `cvtlib.attestations.usable`.
- `profile.py` imports `DECORATIVE_GLYPHS` / `INVISIBLE_CHARS` straight from `cvtlib.ingest` (the local fallback copy is gone).
- Added `tests/integration/test_wave2.py` (5 tests, subprocess `cvt` in a temp `GTJOB_HOME`):
  - junior flow `init` → `ingest` (cv.txt lines equal fixture) → `profile-build` (equals golden) → `profile-cache --store`
    → `jd-check` → `match-check` → `check-tailored` → `render` (1-page PDF), with `status --json` `next_action` checked at every stage;
  - `profile-cache --lookup` hit in a second run; `attest list --person jamie-rivera` on an empty store;
  - the private sample CV (present here, not skipped): one header, no page-number lines, required names present, no `❖`/U+200B;
  - guard test that no `TODO(I-2)` remains in the skill.

## Files changed
- New: `tests/integration/test_wave2.py`, `plan/reports/WP-I2.md`.
- Cross-WP edits (minimal, all wave 2 files):
  1. `cvtlib/provenance.py` (WP-13): removed `_comparable`, `_item_text`, `_highlights`, `_engagement_text`, `_iter_profile`, own
     normalisation; `_usable`, `_merged`, `_item_texts`, `_same` are thin wrappers over the real modules. Imports `comparable` from `profile`.
  2. `cvtlib/checks.py` (WP-13): `_comparable` → `profile.comparable`.
  3. `cvtlib/commands/checks.py` (WP-13): `provenance._usable(...)` → `attestations.usable({"attestations": ...}, run_id=, include_proposed=True)`.
  4. `cvtlib/profile.py` (WP-10): (a) `merged_view` / `active_corrections` gain keyword `statuses` (default `("active",)`, so behaviour is
     unchanged); provenance needs active + this run's proposed corrections (rule 6). (b) skills `item_text` is now `"Name: kw1, kw2"`
     (was `"Name kw1 kw2"`), the form the golden `match.json` quotes and provenance rely on. `test_profile.py` still passes.
     (c) direct `from .ingest import ...`.

## Acceptance
```
$ rg -n "TODO\(I-2\)" .claude/ src/ tests/ ; test $? -eq 1 && echo "no stand-ins"
no stand-ins
```
```
$ uv run pytest -q tests/unit tests/integration        (log: .cache/logs/WP-I2/all.log)
FAILED tests/unit/test_state.py::test_create_run_layout - AssertionError: assert 'cursor' == 'unknown'
FAILED tests/unit/test_state.py::test_host_detection_and_history - AssertionError: assert 'cursor' == 'unknown'
2 failed, 573 passed, 1 skipped in 26.88s
```
```
$ uv run pytest -q tests/integration/test_wave2.py     (log: .cache/logs/WP-I2/w2.log)
5 passed in 4.68s
```
```
$ env -u CLAUDECODE -u CURSOR_* ... uv run pytest -q tests/unit/test_state.py
30 passed in 0.19s
```

## Deviations
- `profile-build` output equals the golden profile except for the `created_at` timestamp and one script-origin
  info `missing_contact` issue (the golden has no phone; WP-10 documents this). The test asserts exactly that one issue, then compares the rest.
- `check-tailored` moves `answers_applied` → `tailored`, so the test expects `tailored` after it (no `assemble` exists yet).
  The Helm attestation (`att-001`) is added with `cvtlib.attestations` (proposed, run-scoped) and activated before forcing `approved`.
- Before approval the `attestation_status` gate is `warn`; at `approved` it is `pass` once `att-001` is active.

## Open issues
- `tests/unit/test_state.py::test_create_run_layout` and `::test_host_detection_and_history` fail when pytest runs inside
  Cursor or Claude Code (`hostdetect` reads `CURSOR_*` / `CLAUDECODE`). Fix, for the owner of `tests/conftest.py`: have the
  `workspace` fixture `delenv` `CLAUDECODE` and every `CURSOR_*` variable. Not edited here (not owned).
- WP-09 ESCALATION (state schema `ingest.method` lacks `ocr`) is still open; it is outside this WP.
- `item_text` for unknown IDs raises in `profile.py` while provenance used to return `""`. Provenance only calls it for IDs
  taken from `iter_items`, so no behaviour change.
