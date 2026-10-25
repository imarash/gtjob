# WP-G5: Final acceptance

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (after WP-I5) | Everything | Opus (`cv-reviewer`, read-only) + the human owner for the host checklist | L |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G5.md`.

**WPs in this wave:** WP-25, WP-26, WP-I5. Final acceptance covers the whole product.

## Hard gates (all must pass)

1. `uv run pytest -q tests` passes with zero skips on the orchestrator machine (private goldens present).
2. `cvt lint-skill --all` exits 0. `cvt package-skill` produces a zip with no personal data (the WP-I5 grep).
3. A fresh-clone check: `rm -rf .cache/fresh && git clone -q . .cache/fresh && (cd .cache/fresh && uv run pytest -q tests/unit)`.
   This stays inside the workspace, because the Cursor sandbox only allows writes there.
   It passes, with private-dependent tests skipping cleanly. This proves that no committed file needs personal data.
4. The canonical exchange, from the e2e suite (WP-25):
   - The attestations `att-001`…`att-005` are created with the right scope.
   - The final CV is exactly 2 pages, with every gate passing.
   - The second JD run does not re-ask about service mesh, Istio, or TypeScript.
5. Every truthfulness guard test (WP-25) passes.

## Live checks (need `ANTHROPIC_API_KEY`; the orchestrator runs them if you cannot)

6. `uv run pytest -q evals -m live`:
   - Interaction cases pass.
   - The judge has a mean ≥ 4.0, no criterion ≤ 2, and truthfulness ≥ baseline.
   - Trigger recall ≥ 0.9 with no false positives.
   - 3-run consistency holds.
   - The token-budget eval (WP-23): the new-JD run is ≤ 1.25 × the budget totals. Record the actual input, cache
     read, and output tokens per stage, and the cost estimate.

   Record the numbers in the report.

## Human checks

7. `evals/HOST-CHECKLIST.md` is executed by the user in Cursor and in Claude Code. The orchestrator pastes the
   ticked checklist into `plan/reports/WP-G5-host-checklist.md`. If it is missing, the verdict is "APPROVE pending
   host checklist".

## Final review

8. View the sample PDF pages and `report.md` (WP-I5 left the PNGs in `.cache/review/`) and give an honest
   hiring-manager verdict with the top 3 improvements for a v2.
9. Review the open-question defaults in `plan/PLAN.md`. Note any that the build proved wrong.

Verdict: **APPROVE** (final acceptance) when 1-5 pass and 6 passes or was run with documented exceptions. Otherwise
**FIX-UPS**, with briefs.
