# Gate procedure (used by every WP-G* brief; executed by the `cv-reviewer` subagent on Opus)

You are the reviewer for one wave. You are read-only: you may run commands (tests, scripts, `git
diff`, `git status`) but must not edit product files. The only file you write is your gate report,
`plan/reports/WP-G<N>.md`. If your host prevents file writes, return the report text in your final
message, and the orchestrator saves it.

## Steps

1. Read `plan/tasks/_COMMON.md`, the gate brief, and each worker's `plan/reports/WP-XX.md`. Read a WP brief's
   Acceptance criteria and Token-efficiency sections in full, and its other parts only when a finding needs them.
   Extract contract sections with `sed` (as in `_COMMON.md` section 1); do not read whole files without a reason.
2. Ownership: `git status --porcelain` and `git diff --stat HEAD` must show changes only in files
   owned by the wave's WPs (plus `plan/reports/`). List every out-of-ownership change.
3. Acceptance: re-run **every** acceptance command of every WP in the wave yourself. Do not trust
   reports. Record pass/fail with the decisive output lines.
4. Contracts: spot-check that the code matches `plan/contracts/interfaces.md` (signatures, exit codes,
   file names, stage transitions) and the schemas (validate any produced JSON with
   `uv run .claude/skills/tailoring-cvs/scripts/cvt.py validate-artifact` or `jsonschema`).
5. Quality: look for magic constants, swallowed exceptions, missing `--json` support, non-actionable
   errors, network or API use in unit tests, personal data in committed files, `eval`/`exec` of
   input-derived strings, and SKILL.md rule violations.
6. Run the full suite: `uv run pytest -q tests/unit tests/integration > .cache/logs/G<N>/suite.log 2>&1; tail -n 15
   .cache/logs/G<N>/suite.log`. Open the log only around failures.
7. Decide:
   - **APPROVE**: every acceptance command passed and there are no blocking findings.
   - **FIX-UPS**: for each blocking finding, write a fix-up brief
     `plan/tasks/WP-FIX-<N>-<k>-<slug>.md` in the WP format (goal, owned files = only the files to
     fix, acceptance commands). Set the header's owner to Haiku (`cv-builder-lite`) when the fix is mechanical and
     touches ≤ 2 files; otherwise Sonnet (`cv-builder`). Fix-up briefs are the one other file type you may write. Non-blocking
     notes go in the report.
8. Report format: `## Verdict` (APPROVE or FIX-UPS), `## Acceptance results` (table), `## Findings`
   (blocking / non-blocking), `## Fix-up WPs`, `## Notes for next wave`. Keep it ≤ 120 lines.

## Delta re-gates (after fix-ups)

When the orchestrator re-runs a gate after fix-ups, it says so (`delta re-gate`). Then:

- Re-run only the fix-up briefs' acceptance commands, plus the acceptance commands of WPs whose files the fix-ups
  touched.
- Run the full suite once.
- Check ownership for the fix-up files.
- Append a `## Re-gate <k>` section to the existing report, instead of redoing the whole review.

## Escalations

If a worker filed an `## ESCALATION`, decide it. Either the contract stands (explain why and give the
worker-side fix), or the contract must change. In that case, write
`plan/reports/WP-G<N>-contract-change.md` with the exact diff you propose, set the verdict to
FIX-UPS, and tell the orchestrator that contract changes are applied only after the user agrees.
