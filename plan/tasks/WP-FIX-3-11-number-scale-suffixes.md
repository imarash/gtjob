# WP-FIX-3-11: `trillion`, `bn`/`mn`/`tn`/`T`, and `lakh`/`crore` count as number scales (truthfulness rule 5)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 3) | WP-FIX-3-9 | Haiku (`cv-builder-lite`) | S |

## Goal

`lexicon.numbers()` knows the scale words `thousand`, `million`, `billion` and the glued digit suffixes `k`, `m`,
`b`. Any other scale is silently dropped, and the bare digits remain. At re-gate 3, `assemble` plus
`provenance.check_tailored` on the junior golden plan accepted all four of these invented summary sentences, because
the golden sources contain a `2`:

- "Processed 2bn events." (`numbers` → `["2"]`)
- "Processed $2mn in spend." (`["2"]`)
- "Trained on 2T tokens." (`["2"]`)
- "Processed a trillion events." (`[]`)

Close the whole class in one change, so that no further scale word needs its own fix-up.

## Context

- Read `plan/tasks/_COMMON.md`.
- `cvtlib/lexicon.py`: `MULTIPLIERS`, `NUMBER_WORD_MULTIPLIERS`, `SCALE_WORDS`, `_NUMBER_RE`, `_atoms`, and the
  `numbers()` docstring. `_parse_run` treats every word in `SCALE_WORDS` the same way, and a scale word with no number
  before it yields nothing ("billion" → `[]`). No parser change should be needed beyond the regex.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-3-11.md`

## Steps

1. **Scale words.** Add these to `NUMBER_WORD_MULTIPLIERS` and to `SCALE_WORDS`: `trillion` 10^12, the spaced
   abbreviations `bn` and `bln` 10^9, `mn` and `mln` 10^6, `tn` 10^12, and `lakh` 10^5 and `crore` 10^7. Plurals
   ("trillions", "lakhs") yield nothing, as "millions" does now. Do not add `mm` or `MM`; "5mm" stays `["5"]`.
2. **Glued digit suffixes.** Extend `MULTIPLIERS` with `t` 10^12, `bn` 10^9, `mn` 10^6, and `tn` 10^12. Change the
   suffix group of `_NUMBER_RE` to match, case-insensitively, the longest of `bn|mn|tn|k|m|b|t`, followed by
   `(?![A-Za-z0-9])` as now. For example, use `((?i:bn|mn|tn|[kmbt]))`. Keep the existing fallback: when no suffix
   matches ("5TB", "200ms", "3x"), the bare digits are still the number.
3. Update the `numbers()` docstring examples (one line, for example `2bn` -> `2000000000`, `a trillion` -> `1000000000000`).
4. **Tests** (in `test_lexicon.py`, added to the existing number-word or number-suffix test):
   - New values: `"a trillion requests"` → `["1000000000000"]`; `"two trillion"` → `["2000000000000"]`;
     `"2bn events"` → `["2000000000"]`; `"1.2bn"` → `["1200000000"]`; `"$3mn"` → `["3000000"]`; `"1tn"` →
     `["1000000000000"]`; `"1T tokens"` → `["1000000000000"]`; `"2 bn"` → `["2000000000"]`; `"2 mln"` → `["2000000"]`;
     `"3 bln"` → `["3000000000"]`; `"10 lakh users"` → `["1000000"]`; `"2 crore"` → `["20000000"]`.
   - Unchanged: `"trillions of rows"` → `[]`; `"5TB"` → `["5"]`; `"200ms"` → `["200"]`; `"3x faster"` → `["3"]`;
     `"k8s"` → `[]`; `"S3"` → `[]`; `"5B"` → `["5000000000"]`; `"1.5k"` → `["1500"]`; `"5k+ hosts"` → `["5000"]`;
     `"5mm"` → `["5"]`; `"Minneapolis, MN"` → `[]`; `"Nashville, TN 37201"` → `["37201"]`; `"a million users"` →
     `["1000000"]`; `"two billion five hundred million"` → `["2500000000"]`.
5. Run the full suite. If a golden or fixture now fails, report it under `## ESCALATION` with the exact text. Do not
   edit fixtures, goldens, or other modules.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py tests/unit/test_checks.py   # passes
uv run pytest -q tests/unit tests/integration                                                                              # passes
```

The end-to-end check below must print `['unsupported_number']` for each of the five sentences. Paste its output into
the report.

```bash
PYTHONPATH=.claude/skills/tailoring-cvs/scripts uv run python - <<'EOF'
import sys
sys.path.insert(0, "tests/unit")
import test_assemble as t
from cvtlib import provenance
atts = t._atts("att-001")
for extra in (" Processed 2bn events.", " Processed $2mn in spend.", " Trained on 2T tokens.",
              " Processed a trillion events.", " Served 2 crore users."):
    plan = t._golden("tailor-plan"); plan["summary"]["text"] += extra
    tailored, _ = t._run(plan)
    v = provenance.check_tailored(tailored, t._golden("profile"), atts, run_id="r", draft=False)
    print(repr(extra), [x["code"] for x in v] or "PASSES")
EOF
```
