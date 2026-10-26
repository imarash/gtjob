# WP-FIX-3-9: "billion" counts as a number word (truthfulness rule 5)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 2) | WP-FIX-3-6 | Haiku (`cv-builder-lite`) | S |

## Goal

`lexicon.numbers()` reads `hundred`, `thousand`, `million`, and `dozen` but not `billion`. At re-gate 2, on the junior
golden plan, `assemble` plus `provenance.check_tailored` accepted these invented summary sentences with no violation:

- "Processed a billion events." (`numbers` → `[]`)
- "Processed two billion events." (`numbers` → `["2"]`; it passes because the golden sources contain a 2)

Digits already work (`5B` → `5000000000`). The spelled-out form must match.

## Context

- Read `plan/tasks/_COMMON.md`.
- `cvtlib/lexicon.py`: the constants `NUMBER_WORD_MULTIPLIERS`, `SCALE_WORDS`, `ARTICLE_MULTIPLIER_WORDS`, and the
  `numbers()` docstring. `_parse_run` treats every word in `SCALE_WORDS` the same way, so no parser change should be
  needed.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-3-9.md`

## Steps

1. Add `"billion": 1_000_000_000` to `NUMBER_WORD_MULTIPLIERS` and `"billion"` to `SCALE_WORDS`. Keep the plural
   forms ("billions of events") yielding nothing, the same as "millions".
2. Tests in `test_lexicon.py` (add cases to the existing number-word test):
   - `"a billion events"` → `["1000000000"]`; `"one billion events"` → `["1000000000"]`; `"two billion events"` →
     `["2000000000"]`; `"5 billion"` → `["5000000000"]`; `"1.5 billion"` → `["1500000000"]`;
     `"two billion five hundred million"` → `["2500000000"]`.
   - `"billions of events"` → `[]`; `"a million users"` → `["1000000"]` (unchanged).
3. Run the full suite. If a golden or fixture now fails, report it under `## ESCALATION` with the exact text. Do not
   edit fixtures.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py   # passes
uv run pytest -q tests/unit tests/integration                                                                              # passes
```

In the report, show `lexicon.numbers(...)` output for the two gate sentences above.
