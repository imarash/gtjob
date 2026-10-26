# WP-FIX-3-2: Spelled-out numbers count as numbers (truthfulness rule 5)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3) | WP-13 | Sonnet (`cv-builder`) | S |

## Goal

`lexicon.numbers` finds only digits, so an invented number written as a word passes every check. At the gate, on the
junior run, `cvt assemble` exited 0 for:

- the summary "… Five years of AWS experience." (refs `sum-1`, `exp-1`, `cert-1`, none with a duration);
- a rewrite "Built GitHub Actions pipelines for twenty services …" (ref `exp-1.b1` says 12).

Rule 5 (interfaces.md section 8) says: "Every number from `lexicon.numbers(text)` must appear in the sources." Make
`numbers()` normalize cardinal number words, so rule 5 catches these cases. Both sides (output text and source text)
go through the same function, so "two" in a source supports "2" or "two" in the output.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract line: `grep -n 'def numbers' plan/contracts/interfaces.md` (signature unchanged; examples stay valid).
- `cvtlib/lexicon.py` `numbers()` and `_NUMBER_RE`; callers are `provenance.py` (rule 5). `answers.py` has its own
  `_numbers` and is not in scope.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-3-2.md`

## Steps

1. In `lexicon.py`, add a module-level map of cardinal words: `two` to `nineteen`, `twenty` to `ninety` by tens,
   hyphenated or spaced compounds (`twenty-five`, `twenty five`), and `dozen` → 12. Match case-insensitively, as whole
   words.
   - `one`, `a`, and `an` are excluded (too often not numeric: "one of", "one idea per bullet"). Name the exclusion
     as a constant with a one-line comment.
   - `hundred`, `thousand`, and `million` multiply a preceding number word or digit ("two hundred" → 200, "5
     thousand" → 5000).
2. `numbers(text)` returns digit tokens and normalized word tokens in order of appearance, deduplicated, with the same
   output format as today (`"5"`, `"200"`).
3. Tests in `test_lexicon.py`:
   - `numbers("Five years of AWS")` → `["5"]`; `"twenty-five services"` → `["25"]`; `"a dozen runbooks"` → `["12"]`;
     `"two hundred hosts"` → `["200"]`.
   - `"one of the first"` → `[]`; `"S3"` and `"k8s"` → `[]` (unchanged).
   - The existing digit cases are unchanged.
4. Run the full suite. If a golden or fixture now fails, the cause must be a genuinely unsupported number word in that
   fixture. Do not edit fixtures; report the failure in the report under `## ESCALATION` with the exact text.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_assemble.py   # passes
uv run pytest -q tests/unit tests/integration                                                          # passes
```

In the report, add a one-paragraph manual check: copy `tests/fixtures/golden/junior/tailor-plan.json`, append
" Five years of AWS experience." to `summary.text`, and show that `assemble.assemble(...)` (or the `assemble`
command in a temp `GTJOB_HOME`) now reports `unsupported_number` for `5`.
