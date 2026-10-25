# WP-G4: Gate for wave 4

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (after WP-I4) | WP-20…WP-24, WP-I4 | Opus (`cv-reviewer`, read-only) | L |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G4.md`.

**WPs in this wave:** WP-20, WP-21, WP-22, WP-23, WP-24, WP-I4.

**Focus:**

1. **The sample golden** (`tests/fixtures/private/sample/`, git-ignored), as a hiring manager would judge it:
   - Read the tailored CV pages (PNGs) and `report.md`.
   - Is every claim traceable?
   - Did the canonical exchange land exactly as asked:
     - Istio and TypeScript in skills.
     - SLOs and error budgets only on the two SRE engagements.
     - No invented metrics.
   - Is the result exactly 2 pages, strong, and targeted at the staff platform SRE JD?
   - Compare it against the original CV PDF: what improved, and what was lost that should not have been?
2. **The CLI AI layer:**
   - The untrusted-input wrapping is present.
   - Schemas sent to the API are strict-compatible.
   - The fix loop sends exact violations.
   - There are no API calls in unit tests (grep for `AnthropicClient(` in tests).
   - The cache key covers the model, prompt, schema, and max_tokens.
3. **Interaction parity:**
   - The CLI's prompts, the `--answers` YAML, the non-interactive stop (exit 6), and `continue --text` follow
     sections 7 and 12.
   - A run moves between `cvt` and `gtjob` without loss.
4. **Evals:** they collect cleanly. Live tests skip without credentials. The judge rubric includes the baseline
   comparison. `HOST-CHECKLIST.md` is concrete enough for a human to execute in 20 minutes.
5. **Docs:** accurate commands, and a privacy section covering ZDR and the git-ignore list.

If `ANTHROPIC_API_KEY` is available to you, also run `uv run pytest -q evals -m live -k "jd or triggers" -x` and
report the results. These are non-blocking at this gate.
