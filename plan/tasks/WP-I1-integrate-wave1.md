# WP-I1: Integrate wave 1 (foundation, assets, fixtures, references)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (after WP-01…WP-07, before G1) | WP-01…WP-07 | Haiku (`cv-builder-lite`; re-dispatch to `cv-builder` on PARTIAL) | S |

## Goal

Check that the wave 1 outputs fit together: fixtures validate against the schemas through the real
`cvtlib.schemas`, references match the contracts, and fonts and presets load. Fix only small integration
mismatches.

## Context

- Read `plan/tasks/_COMMON.md` and every `plan/reports/WP-0[1-7].md` (check ESCALATION sections first).
- You may make **minimal** fixes in files owned by wave 1 WPs: a typo, a wrong path, a fixture field that violates
  its schema, or a reference that names a command or flag that differs from interfaces.md section 3. List every
  such edit in your report with its reason. Do not redesign, and never edit `plan/contracts/*`. Contract problems
  go under `## ESCALATION` for the gate.

## Owned files

- `tests/integration/__init__.py` (empty), `tests/integration/test_wave1.py`
- Minimal fixes in wave 1 files (listed in your report)
- `plan/reports/WP-I1.md`

## Steps

1. `test_wave1.py`:
   - Every JSON under `tests/fixtures/golden/junior/` and `tests/fixtures/render/` validates with
     `cvtlib.schemas.validate` against its schema. The file name maps to the schema; the round file maps to
     `subschema("answers","round")`, and `edits-*` maps to edits.
   - `assets/schemas/*.json` are byte-equal to `plan/contracts/*.schema.json`.
   - `presets.json` loads and has `comfortable`, `standard`, `compact`, and the floor values from section 9.
   - Every font file named in `presets.json` or the template constants exists, and an `OFL.txt` sits beside it.
   - Every `cvt <command>` and `--flag` mentioned in `references/*.md` exists in interfaces.md section 3. Parse the
     section 3 table and regex the references.
   - Every reference over 100 lines has `## Contents`, and no reference links to another reference.
   - `interaction-cases.yaml` parses, and its item IDs exist in the WP-03 ID map.
   - The canonical reply file is byte-identical to the text in `prompts/opus-plan-cv-tailor.md`, when that file is
     present.
2. Run the whole unit suite and fix integration failures (minimal edits).

## Token-efficiency requirements (interfaces.md section 14)

- `test_wave1.py` also checks the guide layout:
  - Every stage and writing guide has a `## Core` ≤ 60 lines, and it names its output file and check command.
  - The combined Core lines for the tailor packet (stage-tailor + style-guide + truthfulness) are ≤ 110.
- The golden `profile-map.json` and `tailor-plan.json` validate against their schemas.

## Acceptance criteria

```bash
uv run pytest -q tests/unit tests/integration/test_wave1.py   # passes
git status --porcelain                                       # only wave-1 files, tests/integration/, plan/reports/
```

## Definition of done

The common definition of done. The report lists every cross-WP edit.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-I1.md` under `## ESCALATION`. Do not change it.
