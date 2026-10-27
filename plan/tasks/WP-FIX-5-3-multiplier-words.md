# WP-FIX-5-3: multiplier words ("doubled", "halved", "tenfold") count as numbers

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5) | WP-13, WP-FIX-3-2..3-12 | Sonnet (`cv-builder`) | S |

## Goal

Truthfulness rule 5 (`interfaces.md` section 8): every number from `lexicon.numbers(text)` must appear in the sources.
The WP-G5 probe appended these to the junior golden's first bullet ("Built GitHub Actions pipelines for 12 services, cutting
average deploy time from 25 minutes to 8 minutes."). `provenance.check_tailored` reported **no** violation for any of them:

- ", tripling throughput"
- ", doubling release frequency"
- ", halving incident count"
- ", a tenfold improvement"

Those are invented metrics. Digits ("3x", "40%", "$2M") and cardinal words ("twelve") are already caught.

## Context

- Read `plan/tasks/_COMMON.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`: the number-word constants (`NUMBER_WORD_UNITS`,
  `NUMBER_WORD_TENS`, `NUMBER_WORD_MULTIPLIERS`), `_atoms`, `_parse_run`, `numbers`.
- Keep every existing `numbers()` test passing. The FIX-3 rounds tuned articles, scales, and plurals carefully.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `tests/unit/test_lexicon.py`
- `plan/reports/WP-FIX-5-3.md`

## Steps

1. Add named module constants and make `numbers()` emit a token for:
   - `doubled|doubling|doubles` and `twofold` → `2`
   - `tripled|tripling|triples` and `threefold` → `3`
   - `quadrupled|quadrupling|quadruples` and `fourfold` → `4`
   - `<cardinal word>fold` (`fivefold`..`ninetyfold`, `hundredfold`) → its value. `10-fold` already yields `10`.
   - `half|halved|halving|halves` → `50`. The usual source form is "50%" or "by half", so `50` matches either way.
   Do **not** map bare `double` or `triple`: "double-check" and "triple-A" are not metrics. Case-insensitive, whole words
   only (the existing `_NUMBER_WORD_RE` boundaries). These words never join a run with neighbouring number words.
2. Update the `numbers()` docstring with the new forms.
3. Tests in `test_lexicon.py`: each form above, the `double-check` / `triple-A` negatives, `on behalf of` (no token), and
   one `provenance.check_tailored` case. A bullet whose source is "reduced costs by 50%" may say "halved costs". A
   bullet whose source has no 2 may not say "doubled".
4. Run the e2e suite to confirm that no golden kept-bullet now fails. A source word yields the same token on both sides.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py      # passes
uv run pytest -q tests                                                         # passes, 0 skipped on the orchestrator machine
```
