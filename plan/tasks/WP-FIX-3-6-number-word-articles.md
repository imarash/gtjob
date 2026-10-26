# WP-FIX-3-6: "a hundred", "one million" and similar count as numbers (truthfulness rule 5)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 1) | WP-FIX-3-2 | Haiku (`cv-builder-lite`) | S |

## Goal

WP-FIX-3-2 made `lexicon.numbers()` read cardinal words, but a multiplier after `a`, `an`, or `one` still yields
nothing. At the re-gate, on the junior golden plan, `assemble` plus `provenance.check_tailored` accepted each of these
invented summary sentences with no violation:

- "Scaled the platform to one million users." (`numbers` → `[]`)
- "Grew to a million requests per day." (`[]`)
- "Managed one hundred servers." / "Ran a hundred servers." (`[]`)

"Two thousand hosts" is already caught (`2000`). Invented scale is the most common CV inflation, so these must count.

## Context

- Read `plan/tasks/_COMMON.md`.
- `cvtlib/lexicon.py`: `numbers()`, `_atoms`, `_parse_run`, `_joins`, and the constants `COMPOUND_ONLY_WORD`,
  `NUMBER_WORD_MULTIPLIERS`, `HUNDRED_WORD`, `SCALE_WORDS`. In `_parse_run`, a bare `one` is skipped before it can
  become `cur`, and `a`/`an` are not atoms at all, so `hundred`/`thousand`/`million` then has no `cur` and is dropped.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-3-6.md`

## Steps

1. In `lexicon.py`, when `a`, `an`, or `one` (case-insensitive, whole word) is **immediately** followed (spaces or a
   hyphen only) by `hundred`, `thousand`, `million`, or `dozen`, treat it as the value 1, so the run yields 100, 1000,
   1000000, or 12. Name the article set as a module-level constant with a one-line comment. A bare `a`/`an`/`one`
   that is not followed by a multiplier still yields nothing.
2. Keep every existing behavior: `"one of the first"` → `[]`, `"twenty-one"` → `["21"]`, `"a dozen runbooks"` →
   `["12"]`, `"hundreds of hosts"` → `[]`, digits unchanged.
3. Tests in `test_lexicon.py` (add cases to the existing number-word test):
   - `"one million users"` → `["1000000"]`; `"a million requests"` → `["1000000"]`; `"one hundred servers"` →
     `["100"]`; `"a hundred servers"` → `["100"]`; `"an hundred"` → `["100"]`; `"A thousand tests"` → `["1000"]`;
     `"one hundred and fifty"` → `["150"]`.
   - `"a team of five"` → `["5"]`; `"one of the first"` → `[]`; `"an outage"` → `[]`.
4. Run the full suite. If a golden or fixture now fails, report it under `## ESCALATION` with the exact text. Do not
   edit fixtures.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py   # passes
uv run pytest -q tests/unit tests/integration                                                                              # passes
```

In the report, show `lexicon.numbers(...)` output for the four gate sentences above.
