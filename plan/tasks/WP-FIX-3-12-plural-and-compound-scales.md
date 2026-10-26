# WP-FIX-3-12: plural scales after a number, glued `bln`/`mln`, and compound scales (truthfulness rule 5)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 4) | WP-FIX-3-11 | Haiku (`cv-builder-lite`) | S |

## Goal

`lexicon.numbers()` drops a scale word when it is plural, glued as `bln`/`mln`, or stacked on another scale word. The
bare digits remain. At re-gate 4, `assemble` plus `provenance.check_tailored` on the junior golden plan accepted these
invented summary sentences, because the golden sources contain a `2`:

- "Served 2 crores users." (`numbers` → `["2"]`)
- "Served 2 billions requests." (`["2"]`)
- "Processed 2bln events." (`["2"]`)

The plural case also hides inflation: "5 lakhs users" rewritten as "5 crores users" gives `["5"]` both times. Plurals
after a number are common in Indian and non-native English CVs ("10 lakhs", "2 millions").

A third form gives the wrong value: "5 thousand crore" gives `["5000"]`, not 5×10^10, and "10 lakh crore" gives
`["1000000"]`, so "10 lakh" rewritten as "10 lakh crore" is not caught.

## Context

- Read `plan/tasks/_COMMON.md`.
- `cvtlib/lexicon.py`: `MULTIPLIERS`, `SCALE_WORDS`, `ABBREVIATED_SCALE_WORDS`, `NUMBER_WORD_MULTIPLIERS`,
  `_NUMBER_RE`, `_atoms`, `_parse_run` (the `elif word in SCALE_WORDS:` branch), and `_joins`.
- `_parse_run` already skips a scale word that has no number before it (`if cur is None: continue`), so "trillions of
  rows" stays `[]` as long as the plural reaches that branch as its singular word.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-3-12.md`

## Steps

1. **Plural scale words.** In `_atoms`, when a word ends in `s` and the word without that `s` is in
   `SCALE_WORDS - ABBREVIATED_SCALE_WORDS` (thousand, million, billion, trillion, lakh, crore), treat it as that
   singular word. Store the singular in the atom's `word` field, so that `_parse_run` and `_joins` see `crore`, not
   `crores`. Do not apply the article path to plurals ("a millions" yields nothing). Do not pluralize `hundred`,
   `dozen`, or the abbreviations.
2. **Glued `bln`/`mln`.** Add `bln` 10^9 and `mln` 10^6 to `MULTIPLIERS`, and change the `_NUMBER_RE` suffix group to
   `((?i:bln|mln|bn|mn|tn|[kmbt]))`. Keep the `(?![A-Za-z0-9])` lookahead and the bare-digit fallback.
3. **Compound scales.** In the `_parse_run` scale branch, when `cur is None`, `total` is non-zero, `last` is a scale
   word, and this scale is larger than `last`'s, multiply `total` by this scale and set `last` to this word, instead
   of skipping. "5 thousand crore" → 5×10^10. "two billion five hundred million" must stay 2500000000.
4. Update the `numbers()` docstring with one example line (for example `5 crores` -> `50000000`).
5. **Tests** (add to the existing `test_numbers_normalization` parametrize list):
   - New values: `"2 crores"` → `["20000000"]`; `"5 lakhs users"` → `["500000"]`; `"3 millions users"` →
     `["3000000"]`; `"two billions"` → `["2000000000"]`; `"2 thousands"` → `["2000"]`; `"1.5 trillions"` →
     `["1500000000000"]`; `"2bln"` → `["2000000000"]`; `"2MLN users"` → `["2000000"]`; `"5 thousand crore"` →
     `["50000000000"]`; `"10 lakh crore"` → `["10000000000000"]`; `"a thousand crore"` → `["10000000000"]`.
   - Unchanged: `"trillions of rows"` → `[]`; `"thousands of hosts"` → `[]`; `"hundreds of millions"` → `[]`;
     `"tens of thousands of users"` → `[]`; `"a millions"` → `[]`; `"5,000 crore"` → `["50000000000"]`;
     `"two billion five hundred million"` → `["2500000000"]`; `"2 thousand and 50"` → `["2000", "50"]`;
     `"Moved to a TN town"` → `[]`; `"Minneapolis, MN"` → `[]`; `"5mm"` → `["5"]`; `"2tb disk"` → `["2"]`;
     `"2bn"` → `["2000000000"]`; `"a trillion"` → `["1000000000000"]`.
6. Run the full suite. If a golden or fixture now fails, report it under `## ESCALATION` with the exact text. Do not
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
for extra in (" Served 2 crores users.", " Served 2 billions requests.", " Processed 2bln events.",
              " Served 2mln users.", " Processed 2bn events."):
    plan = t._golden("tailor-plan"); plan["summary"]["text"] += extra
    tailored, _ = t._run(plan)
    v = provenance.check_tailored(tailored, t._golden("profile"), atts, run_id="r", draft=False)
    print(repr(extra), [x["code"] for x in v] or "PASSES")
EOF
```

## Token efficiency

Read only the named parts of `lexicon.py`. Redirect pytest output to `.cache/logs/WP-FIX-3-12/` and read the tail.
