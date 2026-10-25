# WP-I2: Integrate wave 2 (run commands, ingest, profile, attestations, render, provenance)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (after WP-08…WP-13, before G2) | WP-08…WP-13 | Sonnet (`cv-builder`) | M |

## Goal

Replace the parallel-build stand-ins with real imports, and prove that the wave 2 commands chain on the
junior goldens: `init` → `ingest` → profile → jd → match → `check-tailored` → `render`.

## Context

- Read `plan/tasks/_COMMON.md` and every `plan/reports/WP-0[8-9].md` and `WP-1[0-3].md` (check ESCALATION sections
  first).
- Known stand-ins to remove:
  - WP-13's underscore helpers marked `# TODO(I-2)` → `cvtlib.profile.iter_items` / `item_text` / `merged_view`
    and `cvtlib.attestations.usable`.
  - WP-10's local copy of `DECORATIVE_GLYPHS` → import it from `cvtlib.ingest`.
  - Any other `TODO(I-2)` (run `rg -n "TODO\(I-2\)"`).
- You may make **minimal** fixes in wave 2 files, each listed in your report with its reason. Never edit
  `plan/contracts/*`.

## Owned files

- `tests/integration/test_wave2.py`
- Minimal fixes in wave 2 files (listed in your report)
- `plan/reports/WP-I2.md`

## Steps

1. Remove the stand-ins. `rg -n "TODO\(I-2\)" .claude/ src/ tests/` must return nothing afterwards.
2. `test_wave2.py`, in a `GTJOB_HOME` temp workspace using subprocess `cvt` calls:
   - The junior flow: `init` (txt CV, md JD) → `ingest` (assert `cv.txt` lines equal the fixture's) → copy golden
     `profile-map.json` → `profile-build` (the result equals golden `profile.json`) →
     `profile-cache --store` → copy `jd.json` → `jd-check` → copy `match.json` → `match-check`.
   - Then set the stage to `answers_applied` through `cvtlib.state` (wave 3 commands do not exist yet) → copy
     `tailored.json` → `check-tailored` → force `approved` through `cvtlib.state` → `render` → a 1-page PDF.
   - The sample, if `CVs/ArashMorattab-CV-2026-10.pdf` exists: `init` + `ingest`. `cv.txt` keeps one header, has no
     page-number lines, and contains "LPL Financial", "Royal Bank of Canada (RBC)", and
     "Amirkabir University of Technology". It contains no `❖` or U+200B.
   - `status --json` returns the correct `next_action` after each step.
   - `attest list --person jamie-rivera` runs on an empty store.
3. Run the whole unit suite and fix integration failures.

## Acceptance criteria

```bash
rg -n "TODO\(I-2\)" .claude/ src/ tests/ ; test $? -eq 1 && echo "no stand-ins"
uv run pytest -q tests/unit tests/integration   # passes
```

## Definition of done

The common definition of done. The report lists every cross-WP edit.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-I2.md` under `## ESCALATION`. Do not change it.
