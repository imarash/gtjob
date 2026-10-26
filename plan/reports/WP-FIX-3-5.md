# WP-FIX-3-5 report: skill commands work in zsh, profile cache gets stored

## Summary

- `SKILL.md` "Running the scripts": removed the `CVT="..."` assignment. It now states that `$CVT` stands for
  `uv run .claude/skills/tailoring-cvs/scripts/cvt.py` (repo root), tells the reader to type the prefix in full, and
  shows one example line `uv run .claude/skills/tailoring-cvs/scripts/cvt.py status`. `$CVT` stays as the notation.
- `SKILL.md` workflow, profile checklist line: after `$CVT profile-build RUN` it now says
  `then $CVT profile-cache RUN --store`.
- `references/commands.md` line 3: same change as above (no assignment; the prefix is stated).
- `SKILL.md` body is 138 lines (limit 150). No new flags added.

## Files changed

- `.claude/skills/tailoring-cvs/SKILL.md`
- `.claude/skills/tailoring-cvs/references/commands.md`
- `plan/reports/WP-FIX-3-5.md`

No code, tests, contracts, or other WP files touched.

## Acceptance commands

1. `uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all`  → exit 0
   ```
   lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile
   ```
   Log: `.cache/logs/WP-FIX-3-5/lint.log`

2. `uv run pytest -q tests/unit/test_skillcheck.py tests/integration/test_wave3.py tests/integration/test_wave1.py`  → PASS
   - Run 2: `108 passed in 15.43s` (log: `.cache/logs/WP-FIX-3-5/pytest-acceptance-2.log`)
   - Run 1: `1 failed, 107 passed`. The failure was `test_wave3.py::test_checkpoint1_select_matches_round_replay`
     (`cvt answers-apply ... exited 7`, `KeyError: 'terms'`). See Open issues.
   - Isolated repeats of that test: 1 run exit 0 earlier, plus 3 reps exit 0 (`.cache/logs/WP-FIX-3-5/flaky-{1,2,3}.log`).
   - Run 1 log: `.cache/logs/WP-FIX-3-5/pytest-acceptance.log`

3. `rg -n 'CVT=' SKILL.md references/commands.md`  → no matches (rg exit 1), as required.

4. `rg -n 'profile-cache RUN --store' .claude/skills/tailoring-cvs/SKILL.md`  → 1 match (line 55).

5. `wc -l .claude/skills/tailoring-cvs/SKILL.md`  → 138 (body ≤ 150).

6. `uv run pytest -q tests/unit`  → `1 failed, 899 passed, 1 skipped`
   - Failure: `tests/unit/test_briefs.py::test_match_packet_trims_synthetic_profile_and_keeps_must_haves`
     (`warning[budget]: packet ~1879 tokens exceeds the 1800-token budget for match`).
   - Log: `.cache/logs/WP-FIX-3-5/pytest-unit.log`

## Deviations

- The example line in step 1 is a full `uv run ... cvt.py status` line, not a `$CVT status` line. The brief asked for
  "one example line" of this form and the wave3 test parses both forms, so this keeps the command examples valid. The
  `$CVT` notation is still used everywhere else.

## Open issues

1. **`tests/unit/test_briefs.py::test_match_packet_trims_synthetic_profile_and_keeps_must_haves` fails** (1879 vs 1800
   tokens). Packets are built from `references/<stage>.md` "## Core" sections (`briefs.py`), not from `SKILL.md` or
   `commands.md`, so this WP's edits cannot cause it. It is outside this WP's owned files. Likely owner: the stage-match
   guide or the budget in `assets/budgets.json`. Needs a fix-up or a budget decision.
2. **`test_checkpoint1_select_matches_round_replay` failed once, then passed 4 of 4 times**, including in isolation.
   It is intermittent and order-dependent. The traceback is written to a temp HOME, so I could not capture it. A flake
   in `answers-apply` (attestation terms lookup) is likely. Recommend a dedicated look before the next gate.
