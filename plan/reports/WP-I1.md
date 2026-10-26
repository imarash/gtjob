# WP-I1 report: Integrate wave 1

Status: ESCALATED (non-blocking). All acceptance commands pass. One contract gap (critic visual flag) is allowlisted
in the test and listed below for the gate.

## Summary

Added `tests/integration/test_wave1.py` (53 tests) and an empty `tests/integration/__init__.py`. The tests check
that wave 1 fits together:

- Golden junior JSON and render fixtures validate through `cvtlib.schemas` (answers round via `subschema`, edits
  via `edits`, render via `render-model`). The golden directory mapping covers every file.
- `assets/schemas/*.json` are byte-equal to `plan/contracts/*.schema.json`.
- `presets.json` equals the section 9 JSON block exactly (floor, comfortable, standard, compact).
- Fonts named in `FONTS.md` exist, each with an `OFL.txt` beside them.
- Every `cvt` command, `brief` stage, and `--flag` in `references/*.md` exists in section 3 (one allowlisted flag,
  see ESCALATION).
- Every reference over 100 lines has `## Contents`. No reference links to another reference.
- Every stage and writing guide has `## Core` ≤ 60 lines and names its check command. Stage guides also name their
  output file. Tailor packet Core (stage-tailor + style-guide + truthfulness) is 110 lines or fewer.
- `interaction-cases.yaml` parses. Its item IDs are in the WP-03 ID map.
- The canonical question and reply files match the quoted exchange in `prompts/opus-plan-cv-tailor.md`.

No wave-1 file needed a fix. All checks passed on the first run, so there are no cross-WP edits.

## Files changed

- `tests/integration/__init__.py` (new, empty)
- `tests/integration/test_wave1.py` (new)
- `plan/reports/WP-I1.md` (new)

No edits to wave-1 files and none to `plan/contracts/`.

## Acceptance (logs in `.cache/logs/WP-I1/`)

1. `UV_CACHE_DIR=.cache/uv uv run pytest -q tests/unit tests/integration/test_wave1.py` (`accept.log`)
   ```
   ........................................................................ [ 26%]
   ........................................................................ [ 53%]
   ........................................................................ [ 80%]
   ......................................................                   [100%]
   270 passed in 2.41s
   ```
   That is 217 unit tests plus 53 integration tests. The two `test_state.py` failures that WP-04 saw earlier no
   longer reproduce.

2. `git status --porcelain` (after the test run):
   ```
    M plan/STATUS.md
   ?? plan/reports/WP-01.md … WP-07.md
   ?? tests/integration/__init__.py
   ?? tests/integration/test_wave1.py
   ```
   `plan/STATUS.md` shows as modified. I did not touch it; it is outside this WP's files. All other entries are
   wave-1 files, `tests/integration/`, or `plan/reports/`.

## Deviations

- The canonical exchange in the prompt is soft-wrapped. The test joins the wrapped lines with a single space and then
  compares the result byte-for-byte with the two `.txt` files. The files themselves are unchanged.
- The flag check compares against the union of all section 3 flags, not per command. It also allows `--json` and
  `--help` as global flags.
- Core size counts the `## Core` heading and blank lines up to the next heading. This is slightly stricter than
  counting content lines only.
- Writing guides (`style-guide`, `truthfulness`) are only required to name their check command. Stage guides must
  also name their output file, as section 13 specifies.
- `style-guide.md` and `truthfulness.md` are mentioned by name in `stage-tailor.md` as packet inputs. That is a
  mention, not a link, so it is allowed.
- The template font check (`*.typ` files) has nothing to scan yet because WP-12 has not produced templates. It
  passes as a no-op. `presets.json` names no font files.

## ESCALATION

- **File and section:** `plan/contracts/interfaces.md` section 3 (`brief` row), section 13 (`critic` row), and
  section 14.6.
- **Problem:** The critic visual option has two names and no section 3 definition. Section 13 says "PNGs only with
  `--visual`". Section 14.6 and WP-21/WP-22 say `--critic-visual`. Section 3 defines no critic flags on `brief`.
  `references/critic-rubric.md` uses `--visual`, and `tests/unit/test_refs_writing.py` asserts it. Changing the
  reference would break WP-05's test, so I did not change it.
- **Workaround in this WP:** `UNDOCUMENTED_FLAGS = ("--visual",)` in `tests/integration/test_wave1.py`. It is the
  only exception to the section 3 flag check.
- **Proposed fix:** Add the flag to the section 3 `brief` row (`--visual` or `--critic-visual`, pick one), pick the
  same name everywhere (sections 13 and 14.6, WP-21, WP-22, critic-rubric), then delete the allowlist entry.
