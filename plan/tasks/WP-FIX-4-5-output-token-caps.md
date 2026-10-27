# WP-FIX-4-5: raise the CLI output caps (`max_tokens`) so the sample CV's stages fit

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4) | WP-21, WP-29 | Haiku (`cv-builder-lite`) | XS |

## Goal

`gtjob` sends `budgets.json` `stages.<stage>.output` as the API `max_tokens` (`src/gtjob/config.py::max_tokens`). A
reply that hits the cap raises `E_MAX_TOKENS`, which the fix loop does not retry. The gate measured the private
sample's golden AI outputs (compact JSON; `match.json` with its `quote` fields emptied, because `match-check` fills them):

| Stage | chars | tokens at 3.8 c/t | tokens at 3.0 c/t | cap now |
| --- | --- | --- | --- | --- |
| jd | 8,684 | 2,285 | 2,895 | 2,000 |
| match (model part) | 8,769 | 2,308 | 2,923 | 3,000 |
| tailor | 12,400 | 3,263 | 4,133 | 4,000 |
| questions | ~5,270 | 1,387 | ~1,757 | 1,500 |
| profile | 9,242 | 2,432 | 3,081 | 4,000 |

So a live `gtjob tailor` on the staff JD almost certainly fails at the `jd` stage. `interfaces.md` section 14.4 says
budgets are "tunable without a contract change". A doc-sync proposal for the table is in
`plan/reports/WP-G4-contract-change.md`; this fix does not wait for it.

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/assets/budgets.json` (`stages`), `tests/unit/test_briefs.py::test_budgets_file_matches_the_contract`.
- Input budgets stay unchanged. Only the `output` values change.

## Owned files

- `.claude/skills/tailoring-cvs/assets/budgets.json` (only `stages.*.output`)
- `tests/unit/test_briefs.py` (the pinned budgets test and one new test)
- `plan/reports/WP-FIX-4-5.md`

## Steps

1. Set the `output` values to: profile 8000, jd 5000, match 6000, questions 3000, answer_parse 2000, tailor 8000,
   change_request 2000, fix 1500 (unchanged; fix calls already take `max(stage, fix)`), critic 3000.
2. Update `test_budgets_file_matches_the_contract` to the new output values.
3. Add `test_output_caps_have_headroom_for_golden_outputs` in `test_briefs.py`. Use the module-level constants
   `CONSERVATIVE_CHARS_PER_TOKEN = 3.0` and `OUTPUT_HEADROOM = 1.5`. For each pair below, compact-dump the JSON
   (`separators=(",", ":")`, `ensure_ascii=False`; in `match.json` set every `quote` to `""` first) and assert
   `ceil(len(text) / 3.0) * 1.5 <= budgets()["stages"][stage]["output"]`:
   - Junior golden (`tests/fixtures/golden/junior/`, always runs): profile→`profile-map.json`, jd→`jd.json`,
     match→`match.json`, questions→`questions.json`, answer_parse→`answers.round.json`, tailor→`tailor-plan.json`,
     change_request→`edits-001.json`.
   - Private sample (`tests/fixtures/private/sample/`; `pytest.skip` if the folder is absent): profile→`profile-map.json`,
     jd→`jd.json`, match→`match.json`, questions→`questions.json`, answer_parse→`answers.canonical.round.json`,
     tailor→`tailor-plan.json`.
   Never print or assert literal content from the private files; only lengths.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_briefs.py tests/unit/test_gtjob_stages.py tests/unit/test_gtjob_llm.py   # passes (sample test runs, not skips, on the gate machine)
uv run pytest -q tests/unit tests/integration                                                            # passes
uv run pytest -q evals -m "not live"                                                                     # passes
```
